"""
Multi-Agent Workflow Tools

Implements advanced agent patterns for coordinating multiple agents:
- Supervisor Pattern: Central agent delegates to specialized workers
- Swarm Pattern: Agents hand off to each other based on task requirements
- Agent Coordination: Shared state and message passing between agents
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fichero.workflows.types import State, PortDef, DataType
from fichero.workflows.registry import register_tool, get_tool
from fichero.llm import LLMConfig, chat_workflow
from fichero.prompts import compose_system_prompt
from fichero.workflows.tools.agent import _run_agent_loop, _wrap_workflow_tool

logger = logging.getLogger(__name__)


# =============================================================================
# Multi-Agent State Types
# =============================================================================


class MultiAgentState:
    """Extended state for multi-agent coordination."""

    @staticmethod
    def create(
        task: str,
        context: dict[str, Any] | None = None,
        agent_outputs: dict[str, Any] | None = None,
        current_agent: str = "",
        agent_history: list[dict] | None = None,
        iteration: int = 0,
    ) -> dict[str, Any]:
        """Create a multi-agent state dict."""
        return {
            "task": task,
            "context": context or {},
            "agent_outputs": agent_outputs or {},
            "current_agent": current_agent,
            "agent_history": agent_history or [],
            "iteration": iteration,
            "messages": [],
            "final_result": None,
        }


# =============================================================================
# Supervisor Agent Pattern
# =============================================================================


@register_tool(
    name="supervisor_agent",
    display_name="Supervisor Agent",
    description="Orchestrates multiple worker agents to accomplish complex tasks",
    category="agent",
    icon="person.3",
    color="purple",
    uses_llm=True,
    supports_streaming=True,
    input_ports=[
        PortDef(
            id="task",
            name="Task",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Task to delegate to worker agents",
        ),
        PortDef(
            id="context",
            name="Context",
            port_type="input",
            data_type=DataType.ANY,
            required=False,
            description="Additional context for coordination",
        ),
    ],
    output_ports=[
        PortDef(
            id="result",
            name="Result",
            port_type="output",
            data_type=DataType.TEXT,
            description="Final aggregated result",
        ),
        PortDef(
            id="worker_results",
            name="Worker Results",
            port_type="output",
            data_type=DataType.JSON,
            description="Results from each worker agent",
        ),
        PortDef(
            id="execution_log",
            name="Execution Log",
            port_type="output",
            data_type=DataType.ARRAY,
            description="Log of supervisor decisions and worker executions",
        ),
    ],
    config_schema={
        "workers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "tools": {"type": "array", "items": {"type": "string"}},
                    "system_prompt": {"type": "string"},
                },
                "required": ["name", "description"],
            },
            "default": [],
            "description": "Worker agent configurations",
        },
        "supervisor_prompt": {
            "type": "string",
            "default": """You are a supervisor coordinating multiple specialized workers.
Analyze the task and decide which worker(s) should handle it.
You can delegate to one or more workers and aggregate their results.

Available workers:
{workers_description}

Respond with your delegation decision and reasoning.""",
            "description": "System prompt for supervisor",
        },
        "max_iterations": {
            "type": "integer",
            "default": 5,
            "description": "Maximum delegation rounds",
        },
        "aggregation_strategy": {
            "type": "string",
            "enum": ["sequential", "parallel", "best_of"],
            "default": "sequential",
            "description": "How to combine worker results",
        },
    },
)
async def supervisor_agent(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Execute a supervisor agent that coordinates worker agents.

    The supervisor:
    1. Analyzes the task
    2. Decides which worker(s) to delegate to
    3. Collects and aggregates worker results
    4. Returns final synthesized result
    """
    task = inputs.get("task", "")
    context = inputs.get("context", {})
    workers_config = inputs.get("workers", [])
    supervisor_prompt = inputs.get("supervisor_prompt", "")
    max_iterations = inputs.get("max_iterations", 5)
    aggregation_strategy = inputs.get("aggregation_strategy", "sequential")

    if not task:
        return {
            "result": "",
            "worker_results": {},
            "execution_log": [],
            "error": "No task provided",
        }

    if not workers_config:
        return {
            "result": "",
            "worker_results": {},
            "execution_log": [],
            "error": "No workers configured",
        }

    try:
        execution_log = []
        worker_results = {}

        # Build workers description for supervisor prompt
        workers_desc = "\n".join(
            [
                f"- {w['name']}: {w.get('description', 'No description')}"
                for w in workers_config
            ]
        )

        # Format supervisor prompt
        formatted_prompt = supervisor_prompt.replace(
            "{workers_description}", workers_desc
        )

        # Create supervisor decision function
        async def get_supervisor_decision(
            task_text: str, context_dict: dict, previous_results: dict
        ) -> dict:
            """Get supervisor's delegation decision."""
            messages = [
                {
                    "role": "system",
                    "content": compose_system_prompt(
                        role="agent",
                        extra=formatted_prompt,
                    ),
                },
            ]

            # Add context if provided
            if context_dict:
                context_str = "\n".join(f"{k}: {v}" for k, v in context_dict.items())
                messages.append({"role": "system", "content": f"Context:\n{context_str}"})

            # Add previous results if any
            if previous_results:
                results_str = "\n".join(
                    f"{k}: {v}" for k, v in previous_results.items()
                )
                messages.append(
                    {
                        "role": "system",
                        "content": f"Previous worker results:\n{results_str}",
                    }
                )

            messages.append(
                {
                    "role": "user",
                    "content": f"Task: {task_text}\n\nDecide which worker(s) should handle this task.",
                }
            )

            response = await chat_workflow(messages, llm_config)

            # Parse delegation decision (simplified - in production, use structured output)
            decision = {
                "reasoning": response,
                "workers": [],
                "done": False,
            }

            # Check for worker mentions in response
            content_lower = response.lower()
            for worker in workers_config:
                if worker["name"].lower() in content_lower:
                    decision["workers"].append(worker["name"])

            # Check if supervisor indicates completion
            if (
                "final result" in content_lower
                or "complete" in content_lower
                or "done" in content_lower
            ):
                decision["done"] = True

            return decision

        # Create worker agents
        async def execute_worker(
            worker_config: dict, task_text: str, ctx: dict
        ) -> dict:
            """Execute a single worker agent."""
            worker_tools = []
            for tool_name in worker_config.get("tools", []):
                tool_fn = get_tool(tool_name)
                if tool_fn:
                    worker_tools.append(
                        {
                            "name": tool_name,
                            "tool_fn": tool_fn,
                            "wrapped": _wrap_workflow_tool(
                                tool_name, tool_fn, llm_config
                            ),
                        }
                    )

            worker_prompt = worker_config.get(
                "system_prompt",
                f"You are the {worker_config['name']} agent. {worker_config.get('description', '')}",
            )
            response_text, final_messages, _, _ = await _run_agent_loop(
                task=task_text,
                context=ctx,
                system_prompt=worker_prompt,
                tool_specs=worker_tools,
                llm_config=llm_config,
                max_iterations=10,
            )

            return {
                "worker": worker_config["name"],
                "result": response_text,
                "messages": len(final_messages),
            }

        # Main supervisor loop
        iteration = 0
        current_task = task

        while iteration < max_iterations:
            iteration += 1

            # Get supervisor decision
            decision = await get_supervisor_decision(
                current_task, context, worker_results
            )

            execution_log.append(
                {
                    "iteration": iteration,
                    "decision": decision["reasoning"],
                    "workers_selected": decision["workers"],
                }
            )

            if decision["done"] or not decision["workers"]:
                break

            # Execute selected workers based on aggregation strategy
            if aggregation_strategy == "parallel":
                # Execute all selected workers in parallel

                worker_configs = [
                    w for w in workers_config if w["name"] in decision["workers"]
                ]
                tasks = [
                    execute_worker(w, current_task, context) for w in worker_configs
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for r in results:
                    if isinstance(r, dict) and "worker" in r:
                        worker_results[r["worker"]] = r["result"]
                        execution_log.append(
                            {
                                "iteration": iteration,
                                "worker": r["worker"],
                                "result_preview": r["result"][:200]
                                if r["result"]
                                else "",
                            }
                        )

            elif aggregation_strategy == "best_of":
                # Execute all and pick best (by length as proxy for completeness)

                worker_configs = [
                    w for w in workers_config if w["name"] in decision["workers"]
                ]
                tasks = [
                    execute_worker(w, current_task, context) for w in worker_configs
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                best_result = None
                best_length = 0
                for r in results:
                    if isinstance(r, dict) and "worker" in r:
                        if len(r.get("result", "")) > best_length:
                            best_result = r
                            best_length = len(r.get("result", ""))
                        worker_results[r["worker"]] = r["result"]

                if best_result:
                    execution_log.append(
                        {
                            "iteration": iteration,
                            "best_worker": best_result["worker"],
                            "result_preview": best_result["result"][:200]
                            if best_result["result"]
                            else "",
                        }
                    )

            else:  # sequential
                # Execute workers one by one
                for worker_name in decision["workers"]:
                    worker_config = next(
                        (w for w in workers_config if w["name"] == worker_name), None
                    )
                    if worker_config:
                        result = await execute_worker(
                            worker_config, current_task, context
                        )
                        worker_results[result["worker"]] = result["result"]

                        execution_log.append(
                            {
                                "iteration": iteration,
                                "worker": result["worker"],
                                "result_preview": result["result"][:200]
                                if result["result"]
                                else "",
                            }
                        )

                        # Update context for next worker
                        context = {
                            **context,
                            f"previous_{result['worker']}_result": result["result"],
                        }

        # Generate final aggregated result
        if worker_results:
            # Create summary from all worker results
            results_summary = "\n\n".join(
                [
                    f"**{worker}**:\n{result}"
                    for worker, result in worker_results.items()
                ]
            )

            # Get supervisor to synthesize final result
            final_messages = [
                {
                    "role": "system",
                    "content": compose_system_prompt(
                        role="agent",
                        extra="Synthesize the worker results into a final comprehensive response.",
                    ),
                },
                {
                    "role": "user",
                    "content": f"Original task: {task}\n\nWorker results:\n{results_summary}",
                },
            ]
            final_result = await chat_workflow(final_messages, llm_config)
        else:
            final_result = "No workers executed successfully."

        return {
            "result": final_result,
            "worker_results": worker_results,
            "execution_log": execution_log,
            "iterations": iteration,
        }

    except Exception as e:
        logger.exception(f"Supervisor agent failed: {e}")
        return {
            "result": "",
            "worker_results": {},
            "execution_log": [],
            "error": str(e),
        }


# =============================================================================
# Swarm Agent Pattern
# =============================================================================


@register_tool(
    name="swarm_agent",
    display_name="Swarm Agent",
    description="Agent that dynamically routes to other agents based on task requirements",
    category="agent",
    icon="ant",
    color="orange",
    uses_llm=True,
    supports_streaming=True,
    input_ports=[
        PortDef(
            id="task",
            name="Task",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Task to process",
        ),
        PortDef(
            id="context",
            name="Context",
            port_type="input",
            data_type=DataType.ANY,
            required=False,
            description="Shared context between agents",
        ),
    ],
    output_ports=[
        PortDef(
            id="result",
            name="Result",
            port_type="output",
            data_type=DataType.TEXT,
            description="Final result after agent chain",
        ),
        PortDef(
            id="handoff_chain",
            name="Handoff Chain",
            port_type="output",
            data_type=DataType.ARRAY,
            description="Chain of agent handoffs",
        ),
        PortDef(
            id="shared_context",
            name="Shared Context",
            port_type="output",
            data_type=DataType.JSON,
            description="Final shared context",
        ),
    ],
    config_schema={
        "agents": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "tools": {"type": "array", "items": {"type": "string"}},
                    "system_prompt": {"type": "string"},
                    "can_handoff_to": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "description"],
            },
            "default": [],
            "description": "Available agents in the swarm",
        },
        "entry_agent": {
            "type": "string",
            "default": "",
            "description": "Name of the starting agent",
        },
        "max_handoffs": {
            "type": "integer",
            "default": 10,
            "description": "Maximum number of agent handoffs",
        },
        "handoff_keyword": {
            "type": "string",
            "default": "HANDOFF:",
            "description": "Keyword agents use to initiate handoff",
        },
    },
)
async def swarm_agent(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Execute a swarm of agents that can hand off tasks to each other.

    The swarm pattern allows agents to dynamically route tasks based on
    their specialization. Each agent can decide to:
    1. Handle the task itself
    2. Hand off to another specialized agent
    3. Request more information
    """
    task = inputs.get("task", "")
    context = inputs.get("context", {}) or {}
    agents_config = inputs.get("agents", [])
    entry_agent_name = inputs.get("entry_agent", "")
    max_handoffs = inputs.get("max_handoffs", 10)
    handoff_keyword = inputs.get("handoff_keyword", "HANDOFF:")

    if not task:
        return {
            "result": "",
            "handoff_chain": [],
            "shared_context": {},
            "error": "No task provided",
        }

    if not agents_config:
        return {
            "result": "",
            "handoff_chain": [],
            "shared_context": {},
            "error": "No agents configured",
        }

    # Find entry agent
    entry_agent = None
    if entry_agent_name:
        entry_agent = next(
            (a for a in agents_config if a["name"] == entry_agent_name), None
        )
    if not entry_agent:
        entry_agent = agents_config[0]  # Default to first agent

    try:
        handoff_chain = []
        shared_context = dict(context)
        current_agent = entry_agent
        current_task = task

        for handoff_num in range(max_handoffs):
            # Build agent tools
            agent_tools = []
            for tool_name in current_agent.get("tools", []):
                tool_fn = get_tool(tool_name)
                if tool_fn:
                    agent_tools.append(
                        {
                            "name": tool_name,
                            "tool_fn": tool_fn,
                            "wrapped": _wrap_workflow_tool(
                                tool_name, tool_fn, llm_config
                            ),
                        }
                    )

            # Build system prompt with handoff instructions
            available_handoffs = current_agent.get("can_handoff_to", [])
            handoff_instructions = ""
            if available_handoffs:
                handoff_list = "\n".join(
                    [
                        f"- {name}: {next((a.get('description', '') for a in agents_config if a['name'] == name), '')}"
                        for name in available_handoffs
                    ]
                )
                handoff_instructions = f"""
If you cannot fully handle this task, you can hand off to another agent.
To hand off, include "{handoff_keyword} <agent_name>" in your response.

Available agents to hand off to:
{handoff_list}
"""

            system_prompt = current_agent.get(
                "system_prompt", f"You are the {current_agent['name']} agent."
            )
            full_prompt = f"{system_prompt}\n{handoff_instructions}".strip()

            response_text, _, _, _ = await _run_agent_loop(
                task=current_task,
                context=shared_context,
                system_prompt=full_prompt,
                tool_specs=agent_tools,
                llm_config=llm_config,
                max_iterations=10,
            )

            # Record in handoff chain
            handoff_chain.append(
                {
                    "agent": current_agent["name"],
                    "task": current_task[:200],
                    "response_preview": response_text[:200] if response_text else "",
                }
            )

            # Check for handoff
            if handoff_keyword in response_text:
                # Parse handoff target
                handoff_idx = response_text.index(handoff_keyword)
                after_keyword = response_text[
                    handoff_idx + len(handoff_keyword) :
                ].strip()
                target_name = after_keyword.split()[0].strip() if after_keyword else ""

                # Find target agent
                target_agent = next(
                    (
                        a
                        for a in agents_config
                        if a["name"].lower() == target_name.lower()
                        and a["name"] in available_handoffs
                    ),
                    None,
                )

                if target_agent:
                    # Update context with current agent's work
                    shared_context[f"{current_agent['name']}_output"] = response_text[
                        : response_text.index(handoff_keyword)
                    ].strip()

                    # Extract any task refinement before handoff
                    task_refinement = response_text[
                        handoff_idx + len(handoff_keyword) + len(target_name) :
                    ].strip()
                    if task_refinement:
                        agent_name = current_agent["name"]
                        previous_output = shared_context.get(f"{agent_name}_output", "")
                        current_task = f"Previous context: {previous_output}\n\nRefined task: {task_refinement}"

                    current_agent = target_agent
                    continue

            # No handoff, this is the final result
            return {
                "result": response_text,
                "handoff_chain": handoff_chain,
                "shared_context": shared_context,
            }

        # Max handoffs reached
        return {
            "result": f"Max handoffs ({max_handoffs}) reached. Last response: {response_text}",
            "handoff_chain": handoff_chain,
            "shared_context": shared_context,
            "warning": "Max handoffs reached",
        }

    except Exception as e:
        logger.exception(f"Swarm agent failed: {e}")
        return {
            "result": "",
            "handoff_chain": handoff_chain if "handoff_chain" in dir() else [],
            "shared_context": shared_context if "shared_context" in dir() else {},
            "error": str(e),
        }


# =============================================================================
# Agent Coordinator (for parallel agent execution)
# =============================================================================


@register_tool(
    name="agent_coordinator",
    display_name="Agent Coordinator",
    description="Runs multiple agents in parallel and combines their results",
    category="agent",
    icon="chart.bar.xaxis",
    color="blue",
    uses_llm=True,
    supports_streaming=True,
    input_ports=[
        PortDef(
            id="task",
            name="Task",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Task for all agents",
        ),
        PortDef(
            id="context",
            name="Context",
            port_type="input",
            data_type=DataType.ANY,
            required=False,
            description="Shared context",
        ),
    ],
    output_ports=[
        PortDef(
            id="combined_result",
            name="Combined Result",
            port_type="output",
            data_type=DataType.TEXT,
            description="Synthesized result from all agents",
        ),
        PortDef(
            id="agent_results",
            name="Agent Results",
            port_type="output",
            data_type=DataType.JSON,
            description="Individual results from each agent",
        ),
        PortDef(
            id="agreement_score",
            name="Agreement Score",
            port_type="output",
            data_type=DataType.NUMBER,
            description="How much agents agreed (0-1)",
        ),
    ],
    config_schema={
        "agents": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "system_prompt": {"type": "string"},
                    "tools": {"type": "array", "items": {"type": "string"}},
                    "weight": {"type": "number"},
                },
                "required": ["name"],
            },
            "default": [],
            "description": "Agents to run in parallel",
        },
        "combination_method": {
            "type": "string",
            "enum": ["synthesis", "voting", "weighted_average", "consensus"],
            "default": "synthesis",
            "description": "How to combine agent results",
        },
        "require_consensus": {
            "type": "boolean",
            "default": False,
            "description": "Whether all agents must agree",
        },
    },
)
async def agent_coordinator(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Run multiple agents in parallel and combine their results.

    Useful for:
    - Getting diverse perspectives on a task
    - Ensemble decision making
    - Verification through redundancy
    """

    task = inputs.get("task", "")
    context = inputs.get("context", {})
    agents_config = inputs.get("agents", [])
    combination_method = inputs.get("combination_method", "synthesis")
    require_consensus = inputs.get("require_consensus", False)

    if not task:
        return {
            "combined_result": "",
            "agent_results": {},
            "agreement_score": 0,
            "error": "No task provided",
        }

    if not agents_config:
        return {
            "combined_result": "",
            "agent_results": {},
            "agreement_score": 0,
            "error": "No agents configured",
        }

    try:

        async def run_agent(agent_config: dict) -> dict:
            """Run a single agent."""
            agent_tools = []
            for tool_name in agent_config.get("tools", []):
                tool_fn = get_tool(tool_name)
                if tool_fn:
                    agent_tools.append(
                        {
                            "name": tool_name,
                            "tool_fn": tool_fn,
                            "wrapped": _wrap_workflow_tool(
                                tool_name, tool_fn, llm_config
                            ),
                        }
                    )

            system_prompt = agent_config.get(
                "system_prompt", f"You are agent {agent_config['name']}."
            )
            response_text, _, _, _ = await _run_agent_loop(
                task=task,
                context=context,
                system_prompt=system_prompt,
                tool_specs=agent_tools,
                llm_config=llm_config,
                max_iterations=10,
            )

            return {
                "name": agent_config["name"],
                "result": response_text,
                "weight": agent_config.get("weight", 1.0),
            }

        # Run all agents in parallel
        tasks = [run_agent(agent) for agent in agents_config]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect successful results
        agent_results = {}
        successful_results = []
        for r in results:
            if isinstance(r, dict) and "name" in r:
                agent_results[r["name"]] = r["result"]
                successful_results.append(r)
            elif isinstance(r, Exception):
                logger.warning(f"Agent failed: {r}")

        if not successful_results:
            return {
                "combined_result": "",
                "agent_results": agent_results,
                "agreement_score": 0,
                "error": "All agents failed",
            }

        # Calculate agreement score (simplified - based on response similarity)
        agreement_score = 1.0
        if len(successful_results) > 1:
            # Simple length-based similarity as proxy
            lengths = [len(r["result"]) for r in successful_results]
            avg_length = sum(lengths) / len(lengths)
            variance = sum((ln - avg_length) ** 2 for ln in lengths) / len(lengths)
            agreement_score = max(0, 1 - (variance / (avg_length**2 + 1)))

        # Combine results based on method
        if combination_method == "voting":
            # Simple voting - return most common response (or first if all different)
            combined_result = successful_results[0]["result"]

        elif combination_method == "weighted_average":
            # Use weights to prioritize certain agents
            total_weight = sum(r["weight"] for r in successful_results)
            combined_parts = []
            for r in successful_results:
                weight_pct = r["weight"] / total_weight * 100
                combined_parts.append(
                    f"[{r['name']} ({weight_pct:.0f}% weight)]:\n{r['result']}"
                )
            combined_result = "\n\n".join(combined_parts)

        elif combination_method == "consensus":
            # Check if all agents agree (within threshold)
            if require_consensus and agreement_score < 0.8:
                combined_result = (
                    f"No consensus reached (agreement: {agreement_score:.2f}). Individual results:\n"
                    + "\n\n".join(
                        f"**{r['name']}**: {r['result']}" for r in successful_results
                    )
                )
            else:
                combined_result = successful_results[0]["result"]

        else:  # synthesis
            # Use LLM to synthesize all results
            results_str = "\n\n".join(
                [f"**{r['name']}**:\n{r['result']}" for r in successful_results]
            )

            synthesis_messages = [
                {
                    "role": "system",
                    "content": "Synthesize the following agent responses into a single comprehensive answer. Identify common themes and note any disagreements.",
                },
                {
                    "role": "user",
                    "content": f"Original task: {task}\n\nAgent responses:\n{results_str}",
                },
            ]
            combined_result = await chat_workflow(synthesis_messages, llm_config)

        return {
            "combined_result": combined_result,
            "agent_results": agent_results,
            "agreement_score": agreement_score,
        }

    except Exception as e:
        logger.exception(f"Agent coordinator failed: {e}")
        return {
            "combined_result": "",
            "agent_results": {},
            "agreement_score": 0,
            "error": str(e),
        }
