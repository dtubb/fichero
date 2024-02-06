from langchain_core.runnables import RunnablePassthrough

from langchain.agents import AgentExecutor, BaseMultiActionAgent, Tool
from langchain.schema import AgentAction, AgentFinish
from langchain_core.language_models.chat_models import BaseChatModel
from langchain.chains import LLMChain

from langchain.globals import set_llm_cache

from dotenv import load_dotenv

from pydantic import BaseModel

from langchain_openai.chat_models import ChatOpenAI
from langchain.cache import SQLiteCache

from langchain_core.output_parsers import BaseOutputParser

from langchain.prompts.chat import ChatPromptTemplate
from langchain_community.callbacks import get_openai_callback
from langchain.tools.tavily_search import TavilySearchResults
from langchain.utilities.tavily_search import TavilySearchAPIWrapper
from langchain.pydantic_v1 import BaseModel
import os

from langchain.agents import AgentType, initialize_agent, load_tools
from langgraph.graph import END, Graph

from langchain.globals import set_debug

from langchain.globals import set_verbose

set_debug(False)

set_verbose(True)

set_llm_cache(SQLiteCache(database_path=".langchain.db"))

llm = ChatOpenAI(
    temperature=0.0,
    max_tokens=2000,
    max_retries=100,
    model="gpt-4-1106-preview",
)


NEXT_STEP_TEMPLATE = """You are expert researcher trying answer a question ~250 words. You are asked to answer the following question: {question}

The way you are going to answer the question is as follows:

1. Revise your previous answer using the new information.
    - You should use the previous critique to add important information to your answer.
        _ You MUST include numerical citations in your revised answer to ensure it can be verified.
        - Add a "References" section to the bottom of your answer (which does not count towards the word limit). In form of:
            - [1] https://example.com
            - [2] https://example.com
    - You should use the previous critique to remove superfluous information from your answer and make SURE it is not more than 250 words.
2. Reflect and critique your answer. Specifically, you should:
    - Think about what is missing from your answer.
    - Think about what is superfluous in your answer.
    - Think about what search query you should use next to improve your answer.
  Give your answer in exactly 2 parts. The first should address what is missing from your answer. The second should address what could be removed from your answer. Your should be VERY harsh as we really want to improve the answer.
3. Give the search query you came up with to improve your answer.

Previous steps: 

{previous_steps}

===

Format your answer as follows:

Revised answer: [give your revised answer based on the previous critique and new information from the search engine then the "References" section]
Critique: [give your harsh critique of your revised answer in 2 parts: what is missing and what is superfluous]
Search query: [give the new search query you came up with to enter into the search engine to improve your answer. If you have more than one, make sure they are comma separated and in quotes]

SAY NOTHING else please."""

INITIAL_ANSWER_TEMPLATE = """You are expert researcher trying answer a question ~250 words. You are asked to answer the following question: {question}

The way you are going to answer the question is as follows:

1. Give a detailed in ~250 words.
2. Reflect and critique your answer. Specifically, you should:
    - Think about what is missing from your answer.
    - Think about what is superfluous in your answer.
    - Think about what search query you should use next to improve your answer.
  Give your answer in exactly 2 parts. The first should address what is missing from your answer. The second should address what could be removed from your answer. Your should be VERY harsh as we really want to improve the answer.
3. Give the search query you came up with to improve your answer.

===

Format your answer as follows:

Answer: [give your initial answer]
Critique: [give your harsh critique of your answer in 2 parts: what is missing and what is superfluous]
Search query: [give the search query you came up with to improve your answer. If you have more than one, make sure they are comma separated and in quotes]

SAY NOTHING else please."""


class ReflexionStep(BaseModel):
    """A single step in the reflexion process."""

    answer: str
    critique: str
    search_query: str

    def __str__(self):
        return f"Answer: {self.answer}\nCritique: {self.critique}\nSearch query: {self.search_query}"

def _parse_reflexion_step(output: str) -> tuple[str, str, str]:

    # find answer using .split()
    if ("Answer:" not in output and "Revised answer:" not in output) or not "Critique:" in output or not "Search query:" in output:
        raise ValueError(f"The output is not formatted correctly. Output: {output}")
    if "Answer:" in output:
        answer = output.split("Answer:")[1].split("Critique:")[0].strip()
    else:
        answer = output.split("Revised answer:")[1].split("Critique:")[0].strip()
        
    critique = output.split("Critique:")[1].split("Search query:")[0].strip()
    search_query = output.split("Search query:")[1].strip()
    return answer, critique, search_query

class ReflexionStepParser(BaseOutputParser[ReflexionStep]):
  """Parser for the reflexion step."""

  def parse(self, output: str) -> ReflexionStep:
      """Parse the output."""
      # try to find answer or initial answer
      answer, critique, search_query = _parse_reflexion_step(output)
      return ReflexionStep(
          answer=answer, critique=critique, search_query=search_query
      )

initial_chain = RunnablePassthrough.assign(
  agent_outcome = ChatPromptTemplate.from_template(INITIAL_ANSWER_TEMPLATE) | llm | ReflexionStepParser() | (lambda x: AgentAction(
                  tool="tavily_search_results_json",
                  tool_input=x.search_query,
                  log=str(x),
              ))
)

def prep_next(inputs):
  intermediate_steps = inputs["intermediate_steps"]
  previous_steps = list[str]()

  for i, (action, observation) in enumerate(intermediate_steps, start=1):
      last_step_str = f"""Step {i}:

{action.log}

Search output for "{action.tool_input}":

{observation}"""
      previous_steps.append(last_step_str)

  previous_steps_str = "\n\n".join(previous_steps)
  inputs["previous_steps"] = previous_steps_str
  return inputs
  
next_chain = RunnablePassthrough.assign(
agent_outcome = prep_next | ChatPromptTemplate.from_template(NEXT_STEP_TEMPLATE) | llm | ReflexionStepParser() | (lambda x: AgentAction(
            tool="tavily_search_results_json",
            tool_input=x.search_query,
            log=str(x),
        ))
)

def finish(inputs):
  intermediate_steps = inputs["intermediate_steps"]
  last_action, _ = intermediate_steps[-1]
  last_step_str = last_action.log
  # extract answer
  answer, _, _ = _parse_reflexion_step(last_step_str)

  first_action, _ = intermediate_steps[0]
  first_step_str = first_action.log
  # extract answer
  initial_answer, _, _ = _parse_reflexion_step(first_step_str)

  return AgentFinish(
      log="Reached max steps.",
      return_values={"output": answer, "initial_answer": initial_answer},
  )

def execute_tools(data):
  
  agent_action = data.pop('agent_outcome')
  observation = {t.name: t for t in tools}[agent_action.tool].invoke(agent_action.tool_input)
  data['intermediate_steps'].append((agent_action, observation))
  return data

search = TavilySearchAPIWrapper()
tavily_tool = TavilySearchResults(api_wrapper=search, max_results=5)

tools = [TavilySearchResults(max_results=1)]

workflow = Graph()

# add actors
workflow.add_node("initial", initial_chain)
workflow.add_node("next", next_chain)
workflow.add_node("finish", finish)
workflow.add_node("tools", execute_tools)

# Enter with initial actor, then loop through tools -> next steps until finished
workflow.set_entry_point('initial')

workflow.add_edge('initial', 'tools')
workflow.add_conditional_edges(
    'tools',
    lambda x: "exit" if len(x['intermediate_steps']) >= 1 else "continue",
    {
        "continue": 'next',
        "exit": 'finish'
    }
)
workflow.add_edge('next', 'tools')
workflow.set_finish_point('finish')

chain = workflow.compile()

# Use it!
# chain.invoke({"question": "what is the weather in sf", "intermediate_steps": []})
    
# Streaming Node Output
for output in chain.stream(
    {"question": "What is the best way to start running?", "intermediate_steps": []}
):
    # stream() yields dictionaries with output keyed by node name
    for key, value in output.items():
        print(f"Output from node '{key}':")
        print("---")
        print(value)
    print("\n---\n")
    
    