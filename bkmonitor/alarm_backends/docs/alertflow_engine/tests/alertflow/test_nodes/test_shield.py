"""ShieldNode 和 CircuitBreakerNode 单元测试"""

import unittest
from datetime import datetime, timedelta

from framework.pipeline.context import ProcessContext
from nodes.shield.shield_node import ShieldNode
from nodes.circuit_breaker.circuit_breaker_node import CircuitBreakerNode, CircuitBreaker, CircuitState


class TestShieldNode(unittest.TestCase):
    def _make_node(self, config):
        node = ShieldNode()
        node.initialize(config)
        return node

    def test_no_rules_passes(self):
        node = self._make_node({"shield_rules": []})
        ctx = ProcessContext(event={"severity": 3})
        result = node.process(ctx)
        self.assertTrue(result.is_success)
        self.assertFalse(result.data["shielded"])

    def test_time_range_within(self):
        """时间范围屏蔽 - 在范围内"""
        now = datetime.now()
        node = self._make_node(
            {
                "shield_rules": [
                    {
                        "id": "shield_001",
                        "type": "time_range",
                        "begin_time": (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
                        "end_time": (now + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
                    },
                ],
            }
        )
        ctx = ProcessContext(event={})
        result = node.process(ctx)
        self.assertTrue(result.is_filtered)
        self.assertTrue(ctx.should_stop)

    def test_time_range_outside(self):
        """时间范围屏蔽 - 在范围外"""
        now = datetime.now()
        node = self._make_node(
            {
                "shield_rules": [
                    {
                        "id": "shield_001",
                        "type": "time_range",
                        "begin_time": (now + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
                        "end_time": (now + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
                    },
                ],
            }
        )
        ctx = ProcessContext(event={})
        result = node.process(ctx)
        self.assertTrue(result.is_success)

    def test_dimension_match(self):
        """维度匹配屏蔽"""
        node = self._make_node(
            {
                "shield_rules": [
                    {
                        "id": "shield_002",
                        "type": "dimension",
                        "conditions": {
                            "logic": "and",
                            "conditions": [
                                {"field": "labels.env", "operator": "eq", "value": "staging"},
                            ],
                        },
                    },
                ],
            }
        )
        ctx = ProcessContext(event={"labels": {"env": "staging"}})
        result = node.process(ctx)
        self.assertTrue(result.is_filtered)

    def test_dimension_no_match(self):
        node = self._make_node(
            {
                "shield_rules": [
                    {
                        "id": "shield_002",
                        "type": "dimension",
                        "conditions": {
                            "logic": "and",
                            "conditions": [
                                {"field": "labels.env", "operator": "eq", "value": "staging"},
                            ],
                        },
                    },
                ],
            }
        )
        ctx = ProcessContext(event={"labels": {"env": "production"}})
        result = node.process(ctx)
        self.assertTrue(result.is_success)


class TestCircuitBreaker(unittest.TestCase):
    """CircuitBreaker 熔断器单元测试"""

    def test_initial_state_closed(self):
        cb = CircuitBreaker(failure_threshold=3)
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_transition_to_open(self):
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertFalse(cb.allow_request())

    def test_success_resets_count(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        # 成功后计数重置，再来2次不会触发熔断
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_transition_to_half_open(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0)
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)
        # recovery_timeout=0，立即进入 HALF_OPEN
        import time

        time.sleep(0.01)
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)

    def test_half_open_to_closed(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0)
        cb.record_failure()
        import time

        time.sleep(0.01)
        self.assertTrue(cb.allow_request())
        cb.record_success()
        self.assertEqual(cb.state, CircuitState.CLOSED)


class TestCircuitBreakerNode(unittest.TestCase):
    def _make_node(self, config):
        node = CircuitBreakerNode()
        node.initialize(config)
        return node

    def test_closed_allows_request(self):
        node = self._make_node({"failure_threshold": 5})
        ctx = ProcessContext(event={})
        result = node.process(ctx)
        self.assertTrue(result.is_success)
        self.assertTrue(result.data["allowed"])


if __name__ == "__main__":
    unittest.main()
