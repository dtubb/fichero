#src/sb_slipbox_manager/sb_labs_manager/sb_lab/sb_lab_agent.py

"""
The sb_lab_agent class is the base class for all agents in the LLM lab. It handles integrating with LangChain using the LanGraph
to enable each assistant to create its own sub agents to complete a trask.,

Key capabilities:

- Loads the LangGraph, LangChain module and gets it intialized.rompt type

By inheriting from sb_lab_agent, all subclasses (like the Assistants, etc)
can leverage the same conversational AI/LLM capabilities and the LanGraph workflow. The custom prompt crafting that is u dnerraken in the assistant, allows the allows specializing the chatbot interactions for each agent's role. While the lab_agent allows the material to be extracted clearly.

This provides a common framework for assistants to converse intelligently using LLMs in a way tailored to their particular workflow task.
"""

from src.common import *

# Import langchain's common functions and constants.
from langchain.schema import AgentAction, AgentFinish

from langchain import hub
from langchain.agents import create_openai_functions_agent
from langchain_openai.chat_models import ChatOpenAI

from langchain_core.runnables import RunnablePassthrough
from langchain_core.agents import AgentFinish

from langgraph.graph import END, Graph

from langchain.globals import set_debug
from langchain.globals import set_verbose

from langchain.agents import Tool
from langchain.agents import AgentType, initialize_agent, load_tools

import inspect

class AgentMeta(type):

  # AgentMeta is a metaclass used in the sb_lab_agent inheritance hierarchy to streamline the initialization process. It ensures that when a class such as sb_lab_assistant, which is a subclass of sb_lab_agent, is initialized, all the parameters defined in the subclass's __init__ method are automatically passed up to sb_lab_agent's __init__ method without requiring explicit redeclaration. This simplifies the creation of subclasses by handling common initialization parameters automatically.

  pass

class sb_lab_agent():

  def execute_tools(self, data):
      # Get the most recent agent_outcome - this is the key added in the `agent` above
      agent_action = data.pop('agent_outcome')
      # Get the tool to use
      tool_to_use = {t.name: t for t in self.tools}[agent_action.tool]
      

      # Call that tool on the input
      observation = tool_to_use.invoke(agent_action.tool_input)
      
      # We now add in the action and the observation to the `intermediate_steps` list
      # This is the list of all previous actions taken and their output
      data['intermediate_steps'].append((agent_action, observation))
      
      return data

  # Define logic that will be used to determine which conditional edge to go down
  def should_continue(self, data):
      # If the agent outcome is an AgentFinish, then we return `exit` string
      # This will be used when setting up the graph to define the flow
      if isinstance(data['agent_outcome'], AgentFinish):
          return "exit"
          
      # Otherwise, an AgentAction is returned
      # Here we return `continue` string
      # This will be used when setting up the graph to define the flow

      else:
          return "continue"
        
  # Define logic that will be used to determine which conditional edge to go down
  def should_continue_tools(self, data):

      # If the agent outcome is an AgentFinish, then we return `exit` string
      # This will be used when setting up the graph to define the flow
                 
      if isinstance(data['agent_outcome'], AgentFinish):
          return "exit"
      
      # Otherwise, an AgentAction is returned
      # Here we return `continue` string
      # This will be used when setting up the graph to define the flow
      else:
          return "continue"

  def __init__(self, lab, name):
    self.lab = lab
    self.name = name

    log_and_print(f"Initializing {self.get_name()} in {self.lab.get_name()} lab",
                  LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
    
    self.prompt = "This is a test prompt."
    self.response = "This is a test response"
    self.lab.save_conversation(self.get_name(), self.prompt, self.response)
    
    # Conversation history
    self.conversation_history = []
  
    self.tools = []
    
  def get_name(self):
    return self.name

  def get_tool(self):
    return self.tool
    
  def create_langraph(self):
    self.prompt = hub.pull("hwchase17/openai-functions-agent")

    # Choose the LLM that will drive the agent

    # Check the DEFAULT_LLM constant, and use it, and the appropriate model.
    """
    if DEFAULT_LLM == "openai":
        self.llm = ChatOpenAI(model=f"{DEFAULT_LLM_MODEL}")
    elif DEFAULT_LLM == "ollama":
        # Replace 'ollama_engine' with the appropriate call to create an ollama engine instance
        self.llm = ollama_engine(model=f"{DEFAULT_LLM_MODEL}")
    else:
        raise ValueError("Unsupported LLM engine specified.")    

    log_and_print(f"Initializing {self.get_name()} afent {self.lab.get_name()} lab with LLM {DEFAULT_LLM} and model {DEFAULT_LLM_MODEL}",
                  LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
    
    #Gotta go with OpenAI anyway, as this is is an OPEAN AI Function.
    """

    # Choose the LLM that will drive the agent
    self.llm = ChatOpenAI(model=f"gpt-4")
    
    print("trying 3")
    
    # Construct the OpenAI Functions agent
    self.agent_runnable = create_openai_functions_agent(self.llm, self.tools, self.prompt)
    # Define the agent
    # Note that here, we are using `.assign` to add the output of the agent to the dictionary
    # This dictionary will be returned from the node
    # The reason we don't want to return just the result of `agent_runnable` from this node is
    # that we want to continue passing around all the other inputs
    self.agent = RunnablePassthrough.assign(
        agent_outcome = self.agent_runnable
    )
    print("trying 4")
    # Define the graph
    self.workflow = Graph()

    # >>> ADD THE AGENTS TOOLS TO THE TOOLS HERE <<<<
    # Add the agent node, we give it name `agent` which we will use later
    # Add a node here. Then add an Edge below.
    self.workflow.add_node("agent", self.agent)
    
    # Add the tools node, we give it name `tools` which we will use later
    self.workflow.add_node("tools", self.execute_tools)
  
  
  def compile_langraph(self):
    self.chain = self.workflow.compile()

  def destroy_langraph(self):

    self.graph = None
    self.chain = None
    self.current_node = None
    self.tools = None
    self.workflow = None
    self.prompt = None
    self.llm = None
    self.agent_runnable = None
    self.agent = None
    self.agent_outcome = None
    self.workflow = None
        
    # Reset any other langraph state here
    