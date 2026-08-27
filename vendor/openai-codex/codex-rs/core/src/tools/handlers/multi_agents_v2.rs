//! Implements the MultiAgentV2 collaboration tool surface.

use crate::agent::AgentStatus;
use crate::agent::agent_resolver::resolve_agent_target;
use crate::context::ContextualUserFragment;
use crate::context::InterAgentMessage;
use crate::context::InterAgentMessageType;
use crate::function_tool::FunctionCallError;
use crate::tools::context::ToolInvocation;
use crate::tools::context::ToolOutput;
use crate::tools::context::ToolPayload;
use crate::tools::context::boxed_tool_output;
use crate::tools::handlers::multi_agents_common::*;
use crate::tools::handlers::parse_arguments;
use crate::tools::registry::CoreToolRuntime;
use crate::tools::registry::ToolExecutor;
use codex_protocol::AgentPath;
use codex_protocol::items::CollabAgentTool;
use codex_protocol::items::CollabAgentToolCallItem;
use codex_protocol::items::CollabAgentToolCallStatus;
use codex_protocol::items::SubAgentActivityItem;
use codex_protocol::items::TurnItem;
use codex_protocol::models::ResponseInputItem;
use codex_protocol::openai_models::ReasoningEffort;
use codex_protocol::protocol::InterAgentCommunication;
use codex_protocol::protocol::SubAgentActivityKind;
use codex_tools::ToolName;
use codex_tools::ToolSpec;
use serde::Deserialize;
use serde::Serialize;
use serde_json::Value as JsonValue;
use std::sync::Arc;

pub(crate) use followup_task::Handler as FollowupTaskHandler;
pub(crate) use interrupt_agent::Handler as InterruptAgentHandler;
pub(crate) use list_agents::Handler as ListAgentsHandler;
pub(crate) use send_message::Handler as SendMessageHandler;
pub(crate) use spawn::Handler as SpawnAgentHandler;
pub(crate) use wait::Handler as WaitAgentHandler;

pub(crate) const SPAWN_MODEL_AGENT_TOOL_NAME: &str = "alta_spawn_model_agent";
pub(crate) const SEND_MODEL_MESSAGE_TOOL_NAME: &str = "alta_send_model_message";
pub(crate) const FOLLOWUP_MODEL_TASK_TOOL_NAME: &str = "alta_followup_model_task";

/// Top-level plaintext collaboration alias for tasks that cross model-provider boundaries.
///
/// OpenAI's reserved collaboration tools intentionally return encrypted message arguments. Those
/// payloads can be consumed by another OpenAI model, but third-party providers cannot decrypt
/// them. OpenAI also reserves the complete `collaboration` namespace, so ALTA roles expose these
/// separately named top-level aliases. This keeps the reserved namespace byte-for-byte compatible
/// while cross-provider task content stays portable.
pub(crate) struct PortableCollaborationAlias {
    handler: Arc<dyn CoreToolRuntime>,
    tool_name: &'static str,
    guidance: &'static str,
}

impl PortableCollaborationAlias {
    pub(crate) fn new(
        handler: impl CoreToolRuntime + 'static,
        tool_name: &'static str,
        guidance: &'static str,
    ) -> Self {
        Self {
            handler: Arc::new(handler),
            tool_name,
            guidance,
        }
    }
}

impl ToolExecutor<ToolInvocation> for PortableCollaborationAlias {
    fn tool_name(&self) -> ToolName {
        ToolName::plain(self.tool_name)
    }

    fn spec(&self) -> ToolSpec {
        match self.handler.spec() {
            ToolSpec::Function(mut tool) => {
                tool.name = self.tool_name.to_string();
                tool.description = format!("{} {}", self.guidance, tool.description);
                if let Some(message) = tool
                    .parameters
                    .properties
                    .as_mut()
                    .and_then(|properties| properties.get_mut("message"))
                {
                    message.encrypted = None;
                }
                ToolSpec::Function(tool)
            }
            spec => spec,
        }
    }

    fn exposure(&self) -> codex_tools::ToolExposure {
        self.handler.exposure()
    }

    fn supports_parallel_tool_calls(&self) -> bool {
        self.handler.supports_parallel_tool_calls()
    }

    fn handle(&self, mut invocation: ToolInvocation) -> codex_tools::ToolExecutorFuture<'_> {
        invocation.source = crate::tools::context::ToolCallSource::DirectPlaintextMessage;
        if self.tool_name == SPAWN_MODEL_AGENT_TOOL_NAME
            && let ToolPayload::Function { arguments } = &mut invocation.payload
            && let Ok(JsonValue::Object(mut values)) = serde_json::from_str(arguments)
        {
            values.insert(
                "fork_turns".to_string(),
                JsonValue::String("none".to_string()),
            );
            *arguments = JsonValue::Object(values).to_string();
        }
        self.handler.handle(invocation)
    }
}

impl CoreToolRuntime for PortableCollaborationAlias {
    fn wait_until_ready<'a>(
        &'a self,
        session: &'a Arc<crate::session::session::Session>,
    ) -> Option<futures::future::BoxFuture<'a, ()>> {
        self.handler.wait_until_ready(session)
    }

    fn matches_kind(&self, payload: &ToolPayload) -> bool {
        self.handler.matches_kind(payload)
    }

    fn create_diff_consumer(
        &self,
    ) -> Option<Box<dyn crate::tools::registry::ToolArgumentDiffConsumer>> {
        self.handler.create_diff_consumer()
    }
}

mod followup_task;
mod interrupt_agent;
mod list_agents;
mod message_tool;
mod send_message;
mod spawn;
pub(crate) mod wait;

pub(crate) async fn emit_sub_agent_activity(
    session: &crate::session::session::Session,
    turn: &crate::session::turn_context::TurnContext,
    item: SubAgentActivityItem,
) {
    let item = TurnItem::SubAgentActivity(item);
    session.emit_turn_item_started(turn, &item).await;
    session.emit_turn_item_completed(turn, item).await;
}

fn communication_from_tool_message(
    author: AgentPath,
    recipient: AgentPath,
    message: String,
    source: &crate::tools::context::ToolCallSource,
    trigger_turn: bool,
) -> InterAgentCommunication {
    if !matches!(
        source,
        crate::tools::context::ToolCallSource::DirectPlaintextMessage
    ) {
        return InterAgentCommunication::new_encrypted(
            author,
            recipient,
            Vec::new(),
            message,
            trigger_turn,
        );
    }
    let message_type = if trigger_turn {
        InterAgentMessageType::NewTask
    } else {
        InterAgentMessageType::Message
    };
    let content =
        InterAgentMessage::new(message_type, recipient.clone(), author.clone(), message).render();
    InterAgentCommunication::new(author, recipient, Vec::new(), content, trigger_turn)
}
