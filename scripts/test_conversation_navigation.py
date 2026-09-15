"""Regression contract for preserving a streaming conversation across SPA navigation."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ConversationNavigationContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (ROOT / "app.js").read_text(encoding="utf-8")

    def test_home_render_does_not_discard_the_active_conversation(self) -> None:
        self.assertNotIn(
            'if(state.route==="home"){activeSessionId=null;activeSessionMessages=[];}',
            self.source,
        )
        self.assertIn(
            'if(state.route==="home"){syncConversationRequestControls();',
            self.source,
        )

    def test_stream_owns_messages_independently_of_the_current_view(self) -> None:
        self.assertIn("const conversationRequests = new Set();", self.source)
        self.assertIn(
            "messages:activeSessionMessages,assistantMsg,controller",
            self.source,
        )
        self.assertIn("refreshRequestConversationSurface(requestState);", self.source)
        self.assertIn(
            "conversationCache.get(sessionId)",
            self.source,
        )

    def test_new_conversation_does_not_abort_other_streams(self) -> None:
        start = self.source.index("function startNewConversation()")
        end = self.source.index("document.addEventListener('click'", start)
        self.assertNotIn("abort()", self.source[start:end])
        render = self.source.index("function render()")
        render_end = self.source.index("function ensureCurrentUser", render)
        self.assertNotIn("abort()", self.source[render:render_end])


if __name__ == "__main__":
    unittest.main()
