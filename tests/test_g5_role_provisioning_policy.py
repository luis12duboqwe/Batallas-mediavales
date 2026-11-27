"""Tests for the deliberately incomplete, read-only object inventory."""
import unittest

from ops import ci_g5_role_provisioning as policy
from ops.g5_pg15_writer_fence import Pg15FenceTarget


class PolicyTests(unittest.TestCase):
    def test_explicit_revision_policy_excludes_internal_tables(self):
        for revision in (policy.PREVIOUS, policy.CANDIDATE):
            self.assertFalse(policy.allowed_tables(revision) & policy.INTERNAL_TABLES)
            self.assertEqual(
                policy.expected_tables(revision),
                policy.allowed_tables(revision) | policy.INTERNAL_TABLES,
            )
        self.assertEqual(
            policy.allowed_tables(policy.CANDIDATE) - policy.allowed_tables(policy.PREVIOUS),
            {"wonder_funding", "wonder_contributions"},
        )

    def test_names_must_match_exactly(self):
        names = sorted(policy.expected_tables(policy.PREVIOUS))
        policy.validate_table_names(policy.PREVIOUS, names)
        for invalid in (names + ["unexpected"], names[:-1], names + names[:1],
                        [*names[:-1], None]):
            with self.subTest(invalid=invalid):
                with self.assertRaises(policy.ObjectPolicyError):
                    policy.validate_table_names(policy.PREVIOUS, invalid)
        with self.assertRaises(policy.ObjectPolicyError):
            policy.validate_table_names("head", names)

    def test_read_only_inventory_uses_existing_session_and_rejects_unknown(self):
        class Session:
            def __init__(self):
                self.queries = []
                self.names = sorted(policy.expected_tables(policy.PREVIOUS))

            def query(self, database, sql):
                self.queries.append((database, sql))
                return "\n".join(self.names)

        session = Session()
        target = Pg15FenceTarget("game_ci", "game_app", "postgres")
        policy.inspect_tables(target, session, policy.PREVIOUS)
        self.assertEqual(session.queries[0][0], "game_ci")
        self.assertTrue(session.queries[0][1].startswith("SELECT "))
        session.names.append("unexpected")
        with self.assertRaises(policy.ObjectPolicyError):
            policy.inspect_tables(target, session, policy.PREVIOUS)

    def test_errors_do_not_leak_session_exception(self):
        class Session:
            def query(self, *_):
                raise RuntimeError("sensitive connection information")

        with self.assertRaises(policy.ObjectPolicyError) as error:
            policy.inspect_tables(
                Pg15FenceTarget("game_ci", "game_app", "postgres"),
                Session(), policy.PREVIOUS,
            )
        self.assertNotIn("sensitive", str(error.exception))


if __name__ == "__main__":
    unittest.main()
