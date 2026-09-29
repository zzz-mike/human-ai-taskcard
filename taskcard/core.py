from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATUSES = {
    "draft",
    "ready",
    "in_progress",
    "waiting_approval",
    "blocked",
    "completed",
    "cancelled",
}
WORK_STATUSES = {"pending", "in_progress", "done", "skipped"}
CRITERION_STATUSES = {"pending", "verified", "failed"}


class TaskCardError(RuntimeError):
    pass


class CompletionBlocked(TaskCardError):
    def __init__(self, failures: list[str]):
        self.failures = failures
        super().__init__("\n".join(failures))


def utc_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def slugify(value: str) -> str:
    value = re.sub(r"[^\w\-\u4e00-\u9fff]+", "-", value.strip(), flags=re.UNICODE)
    return value.strip("-").lower() or "task"


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class TaskStore:
    def __init__(self, root: str | Path | None = None):
        configured = root or os.environ.get("TASKCARD_HOME")
        self.root = Path(configured) if configured else Path.cwd() / "task-cards"
        self.root.mkdir(parents=True, exist_ok=True)

    def _card_dir(self, card_id: str) -> Path:
        if not re.fullmatch(r"[\w\-.\u4e00-\u9fff]+", card_id, re.UNICODE):
            raise TaskCardError(f"非法任务卡 ID: {card_id}")
        return self.root / card_id

    def _card_path(self, card_id: str) -> Path:
        return self._card_dir(card_id) / "card.json"

    def list_cards(self) -> list[dict[str, Any]]:
        cards = []
        for path in sorted(self.root.glob("*/card.json")):
            try:
                cards.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return sorted(cards, key=lambda c: c.get("updated_at", ""), reverse=True)

    def get(self, card_id: str) -> dict[str, Any]:
        path = self._card_path(card_id)
        if not path.exists():
            raise TaskCardError(f"任务卡不存在: {card_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def create(self, spec: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        title = str(spec.get("title", "")).strip()
        purpose = str(spec.get("purpose", "")).strip()
        if not title or not purpose:
            raise TaskCardError("任务卡必须包含 title 和 purpose")
        card_id = spec.get("id") or f"{slugify(title)[:40]}-{datetime.now():%Y%m%d}"
        if self._card_path(card_id).exists():
            raise TaskCardError(f"任务卡已存在: {card_id}")

        card = {
            "schema_version": 1,
            "id": card_id,
            "title": title,
            "status": spec.get("status", "draft"),
            "purpose": purpose,
            "background": spec.get("background", ""),
            "current_state": spec.get("current_state", ""),
            "completed_work": list(spec.get("completed_work", [])),
            "pending_work": self._normalize_work(spec.get("pending_work", [])),
            "constraints": list(spec.get("constraints", [])),
            "resources": self._normalize_resources(spec.get("resources", [])),
            "autonomy": {
                "allowed": list(spec.get("autonomy", {}).get("allowed", [])),
                "requires_confirmation": list(
                    spec.get("autonomy", {}).get("requires_confirmation", [])
                ),
            },
            "acceptance_criteria": self._normalize_criteria(
                spec.get("acceptance_criteria", [])
            ),
            "approvals": [],
            "evidence": [],
            "checkpoints": [],
            "created_at": now,
            "updated_at": now,
            "last_started_at": None,
            "version": 1,
        }
        self._validate(card)
        self._save(card, "card_created", {"title": title})
        return card

    def _normalize_work(self, items: list[Any]) -> list[dict[str, Any]]:
        result = []
        for index, item in enumerate(items, 1):
            if isinstance(item, str):
                item = {"title": item}
            result.append(
                {
                    "id": item.get("id") or f"work-{index}",
                    "title": item.get("title", ""),
                    "status": item.get("status", "pending"),
                    "approval_required": bool(item.get("approval_required", False)),
                    "result": item.get("result", ""),
                }
            )
        return result

    def _normalize_resources(self, items: list[Any]) -> list[dict[str, Any]]:
        result = []
        for index, item in enumerate(items, 1):
            if isinstance(item, str):
                item = {"kind": "file", "label": item, "locator": item}
            result.append(
                {
                    "id": item.get("id") or f"resource-{index}",
                    "kind": item.get("kind", "file"),
                    "label": item.get("label") or item.get("locator", ""),
                    "locator": item.get("locator", ""),
                    "required": bool(item.get("required", True)),
                }
            )
        return result

    def _normalize_criteria(self, items: list[Any]) -> list[dict[str, Any]]:
        result = []
        for index, item in enumerate(items, 1):
            if isinstance(item, str):
                item = {"description": item}
            result.append(
                {
                    "id": item.get("id") or f"accept-{index}",
                    "description": item.get("description", ""),
                    "status": item.get("status", "pending"),
                    "evidence_ids": list(item.get("evidence_ids", [])),
                }
            )
        return result

    def _validate(self, card: dict[str, Any]) -> None:
        if card.get("status") not in STATUSES:
            raise TaskCardError(f"非法状态: {card.get('status')}")
        if not card.get("constraints"):
            raise TaskCardError("任务卡必须记录至少一条不可违反的限制")
        if not card.get("acceptance_criteria"):
            raise TaskCardError("任务卡必须记录至少一条验收标准")
        if not card.get("autonomy", {}).get("requires_confirmation"):
            raise TaskCardError("任务卡必须记录需要人工确认的操作")
        if any(x.get("status") not in WORK_STATUSES for x in card["pending_work"]):
            raise TaskCardError("工作项状态非法")
        if any(
            x.get("status") not in CRITERION_STATUSES
            for x in card["acceptance_criteria"]
        ):
            raise TaskCardError("验收项状态非法")

    def _atomic_write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _save(self, card: dict[str, Any], event_type: str, payload: dict[str, Any]) -> None:
        card["updated_at"] = utc_now()
        card["version"] = int(card.get("version", 0)) + 1
        self._validate(card)
        card_dir = self._card_dir(card["id"])
        self._atomic_write(
            card_dir / "card.json",
            json.dumps(card, ensure_ascii=False, indent=2) + "\n",
        )
        event = {
            "at": card["updated_at"],
            "type": event_type,
            "card_id": card["id"],
            "card_version": card["version"],
            "payload": payload,
        }
        with (card_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def environment_snapshot(self, card: dict[str, Any], note: str) -> dict[str, Any]:
        snapshot: dict[str, Any] = {
            "captured_at": utc_now(),
            "cwd": str(Path.cwd()),
            "note": note,
            "resources": [],
        }
        for resource in card.get("resources", []):
            locator = os.path.expanduser(resource.get("locator", ""))
            entry = {
                "id": resource["id"],
                "kind": resource.get("kind"),
                "locator": resource.get("locator"),
                "checked": False,
            }
            if resource.get("kind") in {"file", "directory", "project"} and locator:
                path = Path(locator)
                entry.update(
                    {
                        "checked": True,
                        "exists": path.exists(),
                        "type": "directory" if path.is_dir() else "file" if path.is_file() else "missing",
                    }
                )
                if path.exists():
                    stat = path.stat()
                    entry["modified_at"] = datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).astimezone().isoformat(timespec="seconds")
            snapshot["resources"].append(entry)

        try:
            result = subprocess.run(
                ["git", "status", "--short", "--branch"],
                cwd=Path.cwd(),
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            snapshot["git"] = {
                "available": result.returncode == 0,
                "status": result.stdout.strip(),
            }
        except (OSError, subprocess.SubprocessError):
            snapshot["git"] = {"available": False, "status": ""}

        snapshots = self._card_dir(card["id"]) / "snapshots"
        snapshots.mkdir(parents=True, exist_ok=True)
        filename = datetime.now().strftime("%Y%m%d-%H%M%S") + ".json"
        self._atomic_write(
            snapshots / filename,
            json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        )
        return {"file": str(snapshots / filename), "snapshot": snapshot}

    def start(self, card_id: str, note: str, continuing: bool = False) -> dict[str, Any]:
        card = self.get(card_id)
        if card["status"] in {"completed", "cancelled"}:
            raise TaskCardError(f"任务卡状态为 {card['status']}，不能开始")
        if card["status"] == "draft":
            raise TaskCardError("任务卡仍是 draft；先补全合同并设为 ready")
        pending = [a for a in card["approvals"] if a["status"] == "pending"]
        if pending:
            raise TaskCardError("存在待确认操作；不能继续执行")
        snap = self.environment_snapshot(card, note)
        now = utc_now()
        checkpoint = {
            "id": new_id("checkpoint"),
            "at": now,
            "kind": "environment_snapshot",
            "summary": "继续执行前已重新读取任务卡并检查当前环境" if continuing else "开始执行前已读取任务卡并检查当前环境",
            "verified": snap["file"],
        }
        card["checkpoints"].append(checkpoint)
        card["status"] = "in_progress"
        card["last_started_at"] = now
        self._save(card, "task_continued" if continuing else "task_started", checkpoint)
        return card

    def checkpoint(self, card_id: str, summary: str, verified: str) -> dict[str, Any]:
        card = self.get(card_id)
        item = {
            "id": new_id("checkpoint"),
            "at": utc_now(),
            "kind": "phase",
            "summary": summary,
            "verified": verified,
        }
        card["checkpoints"].append(item)
        self._save(card, "checkpoint_recorded", item)
        return card

    def set_current_state(self, card_id: str, current_state: str) -> dict[str, Any]:
        card = self.get(card_id)
        if not current_state.strip():
            raise TaskCardError("当前状态不能为空")
        previous = card.get("current_state", "")
        card["current_state"] = current_state.strip()
        self._save(
            card,
            "current_state_updated",
            {"previous": previous, "current": card["current_state"]},
        )
        return card

    def update_work(self, card_id: str, work_id: str, status: str, result: str) -> dict[str, Any]:
        if status not in WORK_STATUSES:
            raise TaskCardError(f"非法工作项状态: {status}")
        card = self.get(card_id)
        item = next((x for x in card["pending_work"] if x["id"] == work_id), None)
        if not item:
            raise TaskCardError(f"工作项不存在: {work_id}")
        if status == "done" and item.get("approval_required"):
            approved = any(
                a.get("work_item_id") == work_id and a.get("status") == "approved"
                for a in card["approvals"]
            )
            if not approved:
                raise TaskCardError("该工作项需要人工确认，尚无已批准记录")
        item["status"] = status
        item["result"] = result
        self._save(card, "work_updated", deepcopy(item))
        return card

    def request_approval(
        self, card_id: str, action: str, risk: str, work_item_id: str | None = None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        card = self.get(card_id)
        approval = {
            "id": new_id("approval"),
            "action": action,
            "risk": risk,
            "work_item_id": work_item_id,
            "status": "pending",
            "requested_at": utc_now(),
            "resolved_at": None,
            "resolution_note": "",
        }
        card["approvals"].append(approval)
        card["status"] = "waiting_approval"
        self._save(card, "approval_requested", deepcopy(approval))
        return card, approval

    def resolve_approval(
        self, card_id: str, approval_id: str, approved: bool, note: str
    ) -> dict[str, Any]:
        card = self.get(card_id)
        approval = next((a for a in card["approvals"] if a["id"] == approval_id), None)
        if not approval:
            raise TaskCardError(f"审批项不存在: {approval_id}")
        if approval["status"] != "pending":
            raise TaskCardError("审批项已经处理")
        approval["status"] = "approved" if approved else "rejected"
        approval["resolved_at"] = utc_now()
        approval["resolution_note"] = note
        card["status"] = "in_progress" if approved else "blocked"
        self._save(card, "approval_resolved", deepcopy(approval))
        return card

    def add_evidence(
        self,
        card_id: str,
        criterion_id: str,
        kind: str,
        description: str,
        locator: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        card = self.get(card_id)
        criterion = next(
            (c for c in card["acceptance_criteria"] if c["id"] == criterion_id), None
        )
        if not criterion:
            raise TaskCardError(f"验收项不存在: {criterion_id}")
        evidence = {
            "id": new_id("evidence"),
            "kind": kind,
            "description": description,
            "locator": locator,
            "recorded_at": utc_now(),
            "criterion_ids": [criterion_id],
        }
        card["evidence"].append(evidence)
        criterion["status"] = "verified"
        criterion["evidence_ids"].append(evidence["id"])
        self._save(card, "evidence_recorded", deepcopy(evidence))
        return card, evidence

    def verify(self, card_id: str) -> list[str]:
        card = self.get(card_id)
        failures: list[str] = []
        unfinished = [
            f"{w['id']}:{w['title']}" for w in card["pending_work"] if w["status"] != "done"
        ]
        if unfinished:
            failures.append("仍有未完成工作项: " + ", ".join(unfinished))
        pending_approvals = [a["id"] for a in card["approvals"] if a["status"] == "pending"]
        if pending_approvals:
            failures.append("仍有待确认审批: " + ", ".join(pending_approvals))
        for criterion in card["acceptance_criteria"]:
            if criterion["status"] != "verified":
                failures.append(f"验收项未验证: {criterion['id']} {criterion['description']}")
            elif not criterion["evidence_ids"]:
                failures.append(f"验收项缺少证据: {criterion['id']}")
            else:
                known = {e["id"] for e in card["evidence"]}
                missing = [e for e in criterion["evidence_ids"] if e not in known]
                if missing:
                    failures.append(f"验收项引用了不存在的证据: {criterion['id']}")
        snapshots = [c for c in card["checkpoints"] if c["kind"] == "environment_snapshot"]
        if not snapshots:
            failures.append("缺少开始/继续执行时的环境快照")
        required_missing = []
        if snapshots:
            latest_path = Path(snapshots[-1]["verified"])
            if latest_path.exists():
                latest = json.loads(latest_path.read_text(encoding="utf-8"))
                required_ids = {r["id"] for r in card["resources"] if r.get("required")}
                for resource in latest.get("resources", []):
                    if resource["id"] in required_ids and resource.get("checked") and not resource.get("exists"):
                        required_missing.append(resource["id"])
            else:
                failures.append("最新环境快照文件不存在")
        if required_missing:
            failures.append("必需资源不存在: " + ", ".join(required_missing))
        return failures

    def complete(self, card_id: str) -> dict[str, Any]:
        failures = self.verify(card_id)
        if failures:
            raise CompletionBlocked(failures)
        card = self.get(card_id)
        card["status"] = "completed"
        self._save(card, "task_completed", {"verified_at": utc_now()})
        return card
