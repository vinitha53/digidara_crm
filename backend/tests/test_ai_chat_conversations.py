import os
import unittest
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DIGIDARA_SKIP_AUTO_APP"] = "1"
os.environ["SECRET_KEY"] = "test-ai-chat-secret"
os.environ["JWT_SECRET_KEY"] = "test-ai-chat-jwt-secret"

from flask_jwt_extended import create_access_token

from app import create_app
from extensions import db
from models import AIInteraction, User


class AIChatConversationTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True)
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        user = User(name="Admin", email="admin@example.com", role="admin", is_active=1)
        user.set_password("Admin@1234")
        db.session.add(user)
        db.session.commit()
        self.user_id = user.id
        self.headers = {"Authorization": f"Bearer {create_access_token(identity=str(user.id))}"}
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    @patch("routes.ai_copilot.answer_database_question")
    def test_questions_are_grouped_into_a_persistent_conversation(self, answer_question):
        answer_question.return_value = {
            "answer": "There are 12 leads.",
            "intent": "database_query",
            "sources": "leads",
            "format": "summary",
            "structured": {"title": "Lead count", "points": ["Total leads: 12"]},
            "row_count": 12,
        }
        first = self.client.post(
            "/api/ai-chat/ask",
            json={"prompt": "How many leads are there?"},
            headers=self.headers,
        )
        self.assertEqual(first.status_code, 200)
        conversation_id = first.get_json()["conversation_id"]

        second = self.client.post(
            "/api/ai-chat/ask",
            json={"prompt": "Show me the same lead count", "conversation_id": conversation_id},
            headers=self.headers,
        )
        self.assertEqual(second.status_code, 200)

        conversations = self.client.get("/api/ai-chat/conversations", headers=self.headers)
        self.assertEqual(conversations.status_code, 200)
        self.assertEqual(len(conversations.get_json()), 1)
        self.assertEqual(conversations.get_json()[0]["message_count"], 2)

        history = self.client.get(
            "/api/ai-chat/history",
            query_string={"conversation_id": conversation_id},
            headers=self.headers,
        )
        self.assertEqual(history.status_code, 200)
        self.assertEqual([item["prompt"] for item in history.get_json()], [
            "How many leads are there?",
            "Show me the same lead count",
        ])
        self.assertEqual(AIInteraction.query.filter_by(user_id=self.user_id).count(), 2)


if __name__ == "__main__":
    unittest.main()
