from __future__ import annotations

from app.config import settings
from app.core.gateway import GatewayProcessor
from app.core.state_machine import StateMachine
from app.services.delivery_service import DeliveryService
from app.services.employee_service import EmployeeService
from app.services.openclaw import OpenClawClient
from app.services.scoring_service import ScoringService
from app.services.slack_service import SlackService
from app.services.supabase import SupabaseService
from app.services.telegram_service import TelegramService
from app.services.whatsapp_service import WhatsAppService


supabase_service = SupabaseService(settings=settings)
openclaw_client = OpenClawClient(settings=settings)
slack_service = SlackService(settings=settings)
whatsapp_service = WhatsAppService(settings=settings)
telegram_service = TelegramService(settings=settings)
delivery_service = DeliveryService(
    slack_service=slack_service,
    whatsapp_service=whatsapp_service,
    telegram_service=telegram_service,
)
state_machine = StateMachine()
employee_service = EmployeeService(supabase_service=supabase_service, state_machine=state_machine)
scoring_service = ScoringService(supabase_service=supabase_service)
gateway_processor = GatewayProcessor(
    supabase_service=supabase_service,
    employee_service=employee_service,
    delivery_service=delivery_service,
    openclaw_client=openclaw_client,
    scoring_service=scoring_service,
)
