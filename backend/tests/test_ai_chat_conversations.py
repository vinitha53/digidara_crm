import os
import sys
import types
import unittest
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DIGIDARA_SKIP_AUTO_APP"] = "1"
os.environ["SECRET_KEY"] = "test-ai-chat-secret"
os.environ["JWT_SECRET_KEY"] = "test-ai-chat-jwt-secret"

from flask_jwt_extended import create_access_token

from app import create_app
from extensions import db
from models import AIInteraction, Campaign, Lead, RolePermission, User, WorkflowRule
from routes.ai_copilot import llm_json as real_llm_json, parse_llm_json


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
        self.llm_patch = patch("routes.ai_copilot.llm_json", side_effect=self.fake_llm_json)
        self.llm_patch.start()

    @staticmethod
    def fake_llm_json(system_prompt, payload):
        if "planning component" not in system_prompt:
            return None
        question = payload["question"].lower()
        if "employee" in question or "staff" in question:
            tool = "employees"
        elif "campaign" in question:
            tool = "campaigns"
        elif "workflow" in question:
            tool = "workflows"
        else:
            tool = "leads"
        return {"tool": tool, "query": payload["question"], "owner_requested": False, "owner_id": None}

    def tearDown(self):
        self.llm_patch.stop()
        db.session.remove()
        db.drop_all()
        self.context.pop()

    @patch("routes.ai_copilot.planned_database_answer")
    def test_questions_are_grouped_into_a_persistent_conversation(self, planned_answer):
        planned_answer.return_value = ({
            "answer": "There are 12 leads.",
            "intent": "database_query",
            "sources": "leads",
            "format": "summary",
            "structured": {"title": "Lead count", "points": ["Total leads: 12"]},
            "row_count": 12,
        }, "test-model")
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

    @patch("routes.ai_copilot.planned_database_answer")
    def test_history_storage_is_pruned_to_configured_limits(self, planned_answer):
        planned_answer.return_value = ({
            "answer": "Grounded answer.",
            "intent": "database_query",
            "sources": "leads",
            "format": "summary",
            "structured": {"title": "CRM answer", "points": ["Current data checked"]},
            "row_count": 1,
        }, "test-model")
        self.app.config.update(AI_CHAT_MAX_CONVERSATIONS=2, AI_CHAT_MAX_MESSAGES_PER_CONVERSATION=2)

        first = self.client.post("/api/ai-chat/ask", json={"prompt": "Question one"}, headers=self.headers).get_json()
        conversation_id = first["conversation_id"]
        self.client.post("/api/ai-chat/ask", json={"prompt": "Question two", "conversation_id": conversation_id}, headers=self.headers)
        self.client.post("/api/ai-chat/ask", json={"prompt": "Question three", "conversation_id": conversation_id}, headers=self.headers)

        retained = self.client.get(
            "/api/ai-chat/history", query_string={"conversation_id": conversation_id}, headers=self.headers,
        ).get_json()
        self.assertEqual([row["prompt"] for row in retained], ["Question two", "Question three"])

        self.client.post("/api/ai-chat/ask", json={"prompt": "Second conversation"}, headers=self.headers)
        self.client.post("/api/ai-chat/ask", json={"prompt": "Third conversation"}, headers=self.headers)
        conversations = self.client.get("/api/ai-chat/conversations", headers=self.headers).get_json()
        self.assertEqual(len(conversations), 2)
        self.assertNotIn(conversation_id, [row["id"] for row in conversations])

    @patch("routes.ai_copilot.planned_database_answer")
    def test_follow_up_question_uses_recent_conversation_context(self, planned_answer):
        planned_answer.return_value = ({
            "answer": "Grounded answer.", "intent": "database_query", "sources": "leads",
            "format": "summary", "structured": {"title": "Leads", "points": []}, "row_count": 1,
        }, "test-model")
        first = self.client.post(
            "/api/ai-chat/ask", json={"prompt": "Which leads need attention?"}, headers=self.headers,
        ).get_json()
        self.client.post(
            "/api/ai-chat/ask",
            json={"prompt": "Show those in a table", "conversation_id": first["conversation_id"]},
            headers=self.headers,
        )

        question, context = planned_answer.call_args_list[-1].args
        self.assertEqual(question, "Show those in a table")
        self.assertIn("Which leads need attention?", context[-1]["question"])

    def test_chat_answer_is_calculated_from_current_database_rows(self):
        db.session.add_all([
            Lead(name="Current Lead A", phone="9000000010", service="Course", status="new"),
            Lead(name="Current Lead B", phone="9000000011", service="Project", status="won"),
        ])
        db.session.commit()

        response = self.client.post(
            "/api/ai-chat/ask", json={"prompt": "How many leads are in the CRM?"}, headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["structured"]["metrics"][0]["value"], 2)
        self.assertEqual(body["sources"], "leads")

    def test_chat_returns_requested_lead_name_and_phone_fields(self):
        db.session.add(Lead(name="Raji", phone="7358237370", service="Python Full Stack", status="new"))
        db.session.commit()

        name_and_phone = self.client.post(
            "/api/ai-chat/ask",
            json={"prompt": "I need the phone number of today's lead and name also"},
            headers=self.headers,
        ).get_json()
        name_only = self.client.post(
            "/api/ai-chat/ask",
            json={"prompt": "I need the name of the lead today"},
            headers=self.headers,
        ).get_json()

        self.assertIn("Raji", name_and_phone["response"])
        self.assertIn("7358237370", name_and_phone["response"])
        self.assertIn("Raji", name_only["response"])
        self.assertNotIn("7358237370", name_only["response"])

    def test_staff_chat_is_limited_to_own_profile_and_assigned_leads(self):
        staff = User(name="Current Staff", email="current.staff@example.com", role="staff", is_active=1)
        staff.set_password("Staff@1234")
        other = User(name="Other Employee", email="other.employee@example.com", role="staff", is_active=1)
        other.set_password("Staff@1234")
        db.session.add_all([staff, other])
        db.session.flush()
        db.session.add_all([
            Lead(name="My Assigned Lead", phone="9000000101", service="Course", assigned_to=staff.id),
            Lead(name="Other Assigned Lead", phone="9000000102", service="Course", assigned_to=other.id),
            Lead(name="Unassigned Lead", phone="9000000103", service="Course"),
        ])
        db.session.commit()
        headers = {"Authorization": f"Bearer {create_access_token(identity=str(staff.id))}"}

        employees = self.client.post(
            "/api/ai-chat/ask", json={"prompt": "Show all employee details in a table"}, headers=headers,
        )
        leads = self.client.post(
            "/api/ai-chat/ask", json={"prompt": "Show all leads in a table"}, headers=headers,
        )

        self.assertEqual(employees.status_code, 200)
        employee_body = employees.get_json()
        self.assertEqual(employee_body["row_count"], 1)
        self.assertEqual([row["name"] for row in employee_body["structured"]["table"]["rows"]], ["Current Staff"])
        self.assertNotIn("Other Employee", str(employee_body))

        self.assertEqual(leads.status_code, 200)
        lead_body = leads.get_json()
        self.assertEqual(lead_body["structured"]["metrics"][0]["value"], 1)
        self.assertEqual([row["name"] for row in lead_body["structured"]["table"]["rows"]], ["My Assigned Lead"])
        self.assertNotIn("Other Assigned Lead", str(lead_body))
        self.assertNotIn("Unassigned Lead", str(lead_body))

    @patch("routes.ai_copilot.llm_json")
    def test_staff_profile_remains_self_scoped_when_llm_planner_selects_employees(self, llm_json):
        staff = User(name="Planned Staff", email="planned.staff@example.com", role="staff", is_active=1)
        staff.set_password("Staff@1234")
        other = User(name="Hidden Staff", email="hidden.staff@example.com", role="staff", is_active=1)
        other.set_password("Staff@1234")
        db.session.add_all([staff, other])
        db.session.commit()
        headers = {"Authorization": f"Bearer {create_access_token(identity=str(staff.id))}"}
        llm_json.side_effect = [
            {"tool": "employees", "query": "show every employee in a table"},
            None,
        ]

        response = self.client.post(
            "/api/ai-chat/ask", json={"prompt": "Show all employee details"}, headers=headers,
        )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual([row["name"] for row in body["structured"]["table"]["rows"]], ["Planned Staff"])
        self.assertNotIn("Hidden Staff", str(body))

    @patch("routes.ai_copilot.llm_json")
    def test_staff_is_told_when_a_chat_question_exceeds_their_boundary(self, llm_json):
        staff = User(name="Boundary Staff", email="boundary.staff@example.com", role="staff", is_active=1)
        staff.set_password("Staff@1234")
        other = User(name="Private Employee", email="private.employee@example.com", role="staff", is_active=1)
        other.set_password("Staff@1234")
        db.session.add_all([staff, other])
        db.session.commit()
        headers = {"Authorization": f"Bearer {create_access_token(identity=str(staff.id))}"}
        llm_json.side_effect = [
            {"tool": "leads", "query": "show Private Employee leads", "scope": "named", "owner_requested": True, "owner_id": None},
            {"tool": "employees", "query": "show all employees", "scope": "all", "owner_requested": False, "owner_id": None},
        ]

        named_response = self.client.post(
            "/api/ai-chat/ask", json={"prompt": "Show Private Employee's leads"}, headers=headers,
        )
        company_response = self.client.post(
            "/api/ai-chat/ask", json={"prompt": "Show all employees"}, headers=headers,
        )

        self.assertEqual(named_response.status_code, 200)
        self.assertEqual(company_response.status_code, 200)
        for response in (named_response, company_response):
            body = response.get_json()
            self.assertEqual(body["intent"], "permission_limited")
            self.assertIn("only have permission to view your own profile", body["response"])
            self.assertNotIn("Private Employee", body["response"])

    def test_staff_chat_scopes_granted_campaign_and_workflow_access_to_creator(self):
        staff = User(name="Creator Staff", email="creator.staff@example.com", role="staff", is_active=1)
        staff.set_password("Staff@1234")
        other = User(name="Other Creator", email="other.creator@example.com", role="staff", is_active=1)
        other.set_password("Staff@1234")
        db.session.add_all([staff, other])
        db.session.flush()
        db.session.add_all([
            RolePermission(role="staff", page_key="campaigns", action="view", allowed=1),
            RolePermission(role="staff", page_key="workflows", action="view", allowed=1),
            Campaign(name="My Campaign", channel="email", audience="leads", message_body="Hello", created_by=staff.id),
            Campaign(name="Other Campaign", channel="email", audience="leads", message_body="Hello", created_by=other.id),
            WorkflowRule(name="My Workflow", actions="[]", created_by=staff.id),
            WorkflowRule(name="Other Workflow", actions="[]", created_by=other.id),
        ])
        db.session.commit()
        headers = {"Authorization": f"Bearer {create_access_token(identity=str(staff.id))}"}

        campaigns = self.client.post(
            "/api/ai-chat/ask", json={"prompt": "Show campaigns in a table"}, headers=headers,
        ).get_json()
        workflows = self.client.post(
            "/api/ai-chat/ask", json={"prompt": "Show workflows in a table"}, headers=headers,
        ).get_json()

        self.assertEqual([row["name"] for row in campaigns["structured"]["table"]["rows"]], ["My Campaign"])
        self.assertNotIn("Other Campaign", str(campaigns))
        self.assertEqual([row["name"] for row in workflows["structured"]["table"]["rows"]], ["My Workflow"])
        self.assertNotIn("Other Workflow", str(workflows))

    def test_admin_chat_retains_organization_wide_access(self):
        staff = User(name="Visible Staff", email="visible.staff@example.com", role="staff", is_active=1)
        staff.set_password("Staff@1234")
        db.session.add(staff)
        db.session.flush()
        db.session.add(Lead(name="Organization Lead", phone="9000000199", service="Project", assigned_to=staff.id))
        db.session.commit()

        employees = self.client.post(
            "/api/ai-chat/ask", json={"prompt": "Show all employees in a table"}, headers=self.headers,
        ).get_json()
        leads = self.client.post(
            "/api/ai-chat/ask", json={"prompt": "Show all leads in a table"}, headers=self.headers,
        ).get_json()

        self.assertIn("Visible Staff", [row["name"] for row in employees["structured"]["table"]["rows"]])
        self.assertIn("Organization Lead", [row["name"] for row in leads["structured"]["table"]["rows"]])

    @patch("routes.ai_copilot.llm_json")
    def test_admin_can_query_only_one_named_employees_leads(self, llm_json):
        vinita = User(name="Vinita", email="vinita@example.com", role="staff", is_active=1)
        vinita.set_password("Staff@1234")
        other = User(name="Other Staff", email="another.staff@example.com", role="staff", is_active=1)
        other.set_password("Staff@1234")
        db.session.add_all([vinita, other])
        db.session.flush()
        db.session.add_all([
            Lead(name="Vinita Lead One", phone="9000000201", service="Course", assigned_to=vinita.id),
            Lead(name="Vinita Lead Two", phone="9000000202", service="Project", assigned_to=vinita.id),
            Lead(name="Other Staff Lead", phone="9000000203", service="Course", assigned_to=other.id),
        ])
        db.session.commit()
        llm_json.side_effect = [
            {"tool": "leads", "query": "show Vinita's leads in a table", "owner_requested": True, "owner_id": vinita.id},
            None,
        ]

        response = self.client.post(
            "/api/ai-chat/ask", json={"prompt": "I need to know only Vinita's leads"}, headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["structured"]["metrics"][0]["value"], 2)
        self.assertIn("assigned to Vinita", body["response"])
        self.assertCountEqual(
            [row["name"] for row in body["structured"]["table"]["rows"]],
            ["Vinita Lead One", "Vinita Lead Two"],
        )
        self.assertNotIn("Other Staff Lead", str(body))

    @patch("routes.ai_copilot.llm_json", return_value=None)
    def test_planner_failure_does_not_fall_back_to_a_broad_rule_based_answer(self, _llm_json):
        db.session.add(Lead(name="Must Not Leak", phone="9000000299", service="Course"))
        db.session.commit()

        response = self.client.post(
            "/api/ai-chat/ask", json={"prompt": "Show Vinita's leads"}, headers=self.headers,
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn("planner", response.get_json()["message"].lower())
        self.assertNotIn("Must Not Leak", str(response.get_json()))

    def test_unavailable_groq_model_uses_configured_model_fallback(self):
        calls = []
        request_options = []

        class ModelNotFound(Exception):
            status_code = 404
            body = {"error": {"code": "model_not_found"}}

        class Completions:
            @staticmethod
            def create(**kwargs):
                calls.append(kwargs["model"])
                request_options.append(kwargs)
                if len(calls) == 1:
                    raise ModelNotFound()
                message = types.SimpleNamespace(content='{"tool":"leads","query":"show leads","owner_requested":false,"owner_id":null}')
                return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

        class FakeGroq:
            def __init__(self, api_key):
                self.chat = types.SimpleNamespace(completions=Completions())

        self.app.config.update(
            TESTING=False,
            GROQ_API_KEY="test-key",
            GROQ_MODEL="retired-model",
            GROQ_FALLBACK_MODELS=["openai/gpt-oss-120b"],
        )
        with patch.dict(sys.modules, {"groq": types.SimpleNamespace(Groq=FakeGroq)}):
            result = real_llm_json("planner", {"question": "show leads"})

        self.assertEqual(calls, ["retired-model", "openai/gpt-oss-120b"])
        self.assertEqual(result["tool"], "leads")
        self.assertEqual(request_options[-1]["response_format"], {"type": "json_object"})
        self.assertEqual(request_options[-1]["reasoning_format"], "hidden")

    def test_known_retired_groq_model_is_replaced_before_request(self):
        calls = []

        class Completions:
            @staticmethod
            def create(**kwargs):
                calls.append(kwargs["model"])
                message = types.SimpleNamespace(content='{"tool":"leads","query":"show leads"}')
                return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

        class FakeGroq:
            def __init__(self, api_key):
                self.chat = types.SimpleNamespace(completions=Completions())

        self.app.config.update(
            TESTING=False,
            GROQ_API_KEY="test-key",
            GROQ_MODEL="llama-3.3-70b-versatile",
            GROQ_FALLBACK_MODELS=["qwen/qwen3.6-27b"],
        )
        with patch.dict(sys.modules, {"groq": types.SimpleNamespace(Groq=FakeGroq)}):
            result = real_llm_json("planner", {"question": "show leads"})

        self.assertEqual(calls, ["openai/gpt-oss-120b"])
        self.assertEqual(result["tool"], "leads")

    def test_model_json_parser_ignores_reasoning_and_markdown_wrappers(self):
        content = '<think>private reasoning</think>\nHere is the result:\n```json\n{"tool":"leads","query":"Vinita leads"}\n```'

        result = parse_llm_json(content)

        self.assertEqual(result, {"tool": "leads", "query": "Vinita leads"})

    def test_empty_model_response_uses_next_configured_model(self):
        calls = []

        class Completions:
            @staticmethod
            def create(**kwargs):
                calls.append(kwargs["model"])
                content = "" if len(calls) == 1 else '{"tool":"leads","query":"show leads"}'
                return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=content))])

        class FakeGroq:
            def __init__(self, api_key):
                self.chat = types.SimpleNamespace(completions=Completions())

        self.app.config.update(
            TESTING=False,
            GROQ_API_KEY="test-key",
            GROQ_MODEL="first-model",
            GROQ_FALLBACK_MODELS=["second-model"],
        )
        with patch.dict(sys.modules, {"groq": types.SimpleNamespace(Groq=FakeGroq)}):
            result = real_llm_json("planner", {"question": "show leads"})

        self.assertEqual(calls, ["first-model", "second-model"])
        self.assertEqual(result["tool"], "leads")


if __name__ == "__main__":
    unittest.main()
