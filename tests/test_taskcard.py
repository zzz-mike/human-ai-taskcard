from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from taskcard.core import CompletionBlocked, TaskCardError, TaskStore


def spec() -> dict:
    return {
        "id": "test-card",
        "title": "真实任务",
        "status": "ready",
        "purpose": "验证任务卡状态机",
        "current_state": "尚未执行",
        "constraints": ["不得把候选结果当成完成"],
        "resources": [],
        "autonomy": {
            "allowed": ["读取文件"],
            "requires_confirmation": ["发送消息", "不可恢复删除"],
        },
        "pending_work": [{"id": "work-1", "title": "完成真实步骤"}],
        "acceptance_criteria": [
            {"id": "accept-1", "description": "结果存在且经过核验"}
        ],
    }


class TaskStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = TaskStore(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_persists_and_reopens_from_disk(self) -> None:
        created = self.store.create(spec())
        reopened = TaskStore(self.root).get(created["id"])
        self.assertEqual(reopened["purpose"], "验证任务卡状态机")
        self.assertTrue((self.root / "test-card" / "events.jsonl").exists())

    def test_completion_is_blocked_without_work_snapshot_and_evidence(self) -> None:
        self.store.create(spec())
        with self.assertRaises(CompletionBlocked) as context:
            self.store.complete("test-card")
        message = "\n".join(context.exception.failures)
        self.assertIn("未完成工作项", message)
        self.assertIn("验收项未验证", message)
        self.assertIn("环境快照", message)

    def test_approval_gated_work_requires_approved_record(self) -> None:
        gated = spec()
        gated["pending_work"][0]["approval_required"] = True
        self.store.create(gated)
        with self.assertRaises(TaskCardError):
            self.store.update_work("test-card", "work-1", "done", "不应成功")
        _, approval = self.store.request_approval(
            "test-card", "发送最终消息", "会影响外部人员", "work-1"
        )
        with self.assertRaises(TaskCardError):
            self.store.start("test-card", "审批仍在等待")
        self.store.resolve_approval("test-card", approval["id"], True, "用户明确批准")
        updated = self.store.update_work("test-card", "work-1", "done", "已执行并核验")
        self.assertEqual(updated["pending_work"][0]["status"], "done")

    def test_full_verified_flow_can_complete(self) -> None:
        self.store.create(spec())
        self.store.start("test-card", "已检查临时工作区")
        self.store.update_work("test-card", "work-1", "done", "真实步骤已完成")
        _, evidence = self.store.add_evidence(
            "test-card", "accept-1", "test", "断言通过", str(self.root)
        )
        self.assertTrue(evidence["id"])
        self.assertEqual(self.store.verify("test-card"), [])
        completed = self.store.complete("test-card")
        self.assertEqual(completed["status"], "completed")

    def test_json_remains_parseable_after_updates(self) -> None:
        self.store.create(spec())
        self.store.checkpoint("test-card", "阶段", "核验")
        self.store.set_current_state("test-card", "已完成一个可见阶段")
        path = self.root / "test-card" / "card.json"
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["id"], "test-card")
        self.assertEqual(saved["current_state"], "已完成一个可见阶段")


if __name__ == "__main__":
    unittest.main()
