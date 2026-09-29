#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from taskcard.core import CompletionBlocked, TaskCardError, TaskStore


def dump(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def summary(card: dict) -> dict:
    return {
        "id": card["id"],
        "title": card["title"],
        "status": card["status"],
        "updated_at": card["updated_at"],
        "work": {
            "done": sum(x["status"] == "done" for x in card["pending_work"]),
            "total": len(card["pending_work"]),
        },
        "acceptance": {
            "verified": sum(
                x["status"] == "verified" for x in card["acceptance_criteria"]
            ),
            "total": len(card["acceptance_criteria"]),
        },
        "pending_approvals": sum(
            x["status"] == "pending" for x in card["approvals"]
        ),
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="taskctl", description="人机协作任务卡")
    root.add_argument("--home", help="任务卡数据目录，默认 ./task-cards")
    commands = root.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="从 JSON 文件创建任务卡")
    create.add_argument("--from", dest="source", required=True)

    commands.add_parser("list", help="列出任务卡")

    show = commands.add_parser("show", help="读取完整任务卡")
    show.add_argument("card_id")
    show.add_argument("--json", action="store_true")

    for name in ("start", "continue"):
        command = commands.add_parser(name, help="开始或继续执行并生成环境快照")
        command.add_argument("card_id")
        command.add_argument("--note", required=True)

    checkpoint = commands.add_parser("checkpoint", help="记录阶段结果")
    checkpoint.add_argument("card_id")
    checkpoint.add_argument("--summary", required=True)
    checkpoint.add_argument("--verified", required=True)

    set_state = commands.add_parser("set-state", help="更新任务卡当前真实状态")
    set_state.add_argument("card_id")
    set_state.add_argument("--current", required=True)

    work = commands.add_parser("work", help="更新工作项")
    work.add_argument("card_id")
    work.add_argument("work_id")
    work.add_argument("--status", required=True, choices=("pending", "in_progress", "done", "skipped"))
    work.add_argument("--result", default="")

    request = commands.add_parser("request-approval", help="创建人工审批并暂停")
    request.add_argument("card_id")
    request.add_argument("--action", required=True)
    request.add_argument("--risk", required=True)
    request.add_argument("--work-item")

    approve = commands.add_parser("approve", help="记录用户明确批准")
    approve.add_argument("card_id")
    approve.add_argument("approval_id")
    approve.add_argument("--note", required=True)

    reject = commands.add_parser("reject", help="记录用户拒绝")
    reject.add_argument("card_id")
    reject.add_argument("approval_id")
    reject.add_argument("--note", required=True)

    evidence = commands.add_parser("evidence", help="给验收项添加真实证据")
    evidence.add_argument("card_id")
    evidence.add_argument("--criterion", required=True)
    evidence.add_argument("--kind", required=True)
    evidence.add_argument("--description", required=True)
    evidence.add_argument("--locator", required=True)

    verify = commands.add_parser("verify", help="检查是否满足完成门禁")
    verify.add_argument("card_id")

    complete = commands.add_parser("complete", help="通过门禁后标记完成")
    complete.add_argument("card_id")

    serve = commands.add_parser("serve", help="启动本地任务卡页面")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)
    return root


def human_show(card: dict) -> None:
    print(f"{card['title']}  [{card['status']}]  {card['id']}")
    print(f"\n目标\n{card['purpose']}")
    print(f"\n当前状态\n{card['current_state']}")
    print("\n未完成工作")
    for item in card["pending_work"]:
        gate = " / 需确认" if item["approval_required"] else ""
        print(f"- {item['id']} [{item['status']}]{gate} {item['title']}")
    print("\n验收标准")
    for item in card["acceptance_criteria"]:
        print(
            f"- {item['id']} [{item['status']}] {item['description']} "
            f"(证据 {len(item['evidence_ids'])})"
        )
    pending = [a for a in card["approvals"] if a["status"] == "pending"]
    if pending:
        print("\n等待人工确认")
        for item in pending:
            print(f"- {item['id']} {item['action']} — {item['risk']}")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    store = TaskStore(args.home)
    try:
        if args.command == "create":
            spec = json.loads(Path(args.source).read_text(encoding="utf-8"))
            dump(summary(store.create(spec)))
        elif args.command == "list":
            dump([summary(card) for card in store.list_cards()])
        elif args.command == "show":
            card = store.get(args.card_id)
            dump(card) if args.json else human_show(card)
        elif args.command in {"start", "continue"}:
            card = store.start(
                args.card_id, args.note, continuing=args.command == "continue"
            )
            dump(summary(card))
        elif args.command == "checkpoint":
            dump(summary(store.checkpoint(args.card_id, args.summary, args.verified)))
        elif args.command == "set-state":
            dump(summary(store.set_current_state(args.card_id, args.current)))
        elif args.command == "work":
            dump(summary(store.update_work(args.card_id, args.work_id, args.status, args.result)))
        elif args.command == "request-approval":
            card, approval = store.request_approval(
                args.card_id, args.action, args.risk, args.work_item
            )
            dump({"card": summary(card), "approval": approval})
        elif args.command in {"approve", "reject"}:
            card = store.resolve_approval(
                args.card_id,
                args.approval_id,
                approved=args.command == "approve",
                note=args.note,
            )
            dump(summary(card))
        elif args.command == "evidence":
            card, evidence = store.add_evidence(
                args.card_id,
                args.criterion,
                args.kind,
                args.description,
                args.locator,
            )
            dump({"card": summary(card), "evidence": evidence})
        elif args.command == "verify":
            failures = store.verify(args.card_id)
            dump({"ok": not failures, "failures": failures})
            return 0 if not failures else 2
        elif args.command == "complete":
            dump(summary(store.complete(args.card_id)))
        elif args.command == "serve":
            from taskcard.server import serve

            serve(store, args.host, args.port)
        return 0
    except CompletionBlocked as exc:
        dump({"ok": False, "error": "completion_blocked", "failures": exc.failures})
        return 2
    except (TaskCardError, OSError, json.JSONDecodeError) as exc:
        dump({"ok": False, "error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
