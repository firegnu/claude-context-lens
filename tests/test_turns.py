import unittest

from claude_lens import turns


def _user_text(t):
    return {"role": "user", "content": [{"type": "text", "text": t}]}


def _assistant_tool(name):
    return {"role": "assistant", "content": [{"type": "tool_use", "id": "t", "name": name, "input": {}}]}


def _tool_result():
    return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": "ok"}]}


class SegmentTurnsTest(unittest.TestCase):
    def test_tool_loop_stays_one_turn_then_new_turn(self):
        # req0: user asks; req1: += assistant tool_use + user tool_result (same turn);
        # req2: += assistant text + new user text (new turn)
        bodies = [
            {"messages": [_user_text("do X")]},
            {"messages": [_user_text("do X"), _assistant_tool("Bash"), _tool_result()]},
            {"messages": [_user_text("do X"), _assistant_tool("Bash"), _tool_result(),
                          {"role": "assistant", "content": [{"type": "text", "text": "done"}]},
                          _user_text("now Y")]},
        ]
        result = turns.segment_turns(bodies)
        self.assertEqual([t["index"] for t in result], [0, 1])
        self.assertEqual(result[0]["request_indices"], [0, 1])
        self.assertEqual(result[1]["request_indices"], [2])
        self.assertEqual(result[0]["user_message_preview"], "do X")
        self.assertEqual(result[1]["user_message_preview"], "now Y")
