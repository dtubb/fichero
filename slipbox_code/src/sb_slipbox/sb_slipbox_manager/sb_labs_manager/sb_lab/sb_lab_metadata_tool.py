# src/sb_slipbox_manager/sb_labs_manager/sb_lab/sb_lab_metadata_tool.py

# The sb_lab_metadata_tool extracts metadata from a source document. It is initialized by the sb_lab agent with the full cleaned up text. The tool identified and extracts entities, such as: names of people, places, organizations, dates, and other data. It:
# - Receive source text from the Lab agent
# - Analyze text to identify metadata
# - Undertakes quality assurance on the produced metadata
# - Revised the produced meta data.
# """

from src.common import *
from .sb_lab_assistant import sb_lab_assistant

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

from langchain.tools import StructuredTool  
from langchain.prompts import PromptTemplate

from langchain.chains.llm import LLMChain
from langchain_core.output_parsers import StrOutputParser

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from langchain_community.llms import Ollama

class sb_lab_metadata_tool(sb_lab_assistant):

  def metadata_extraction_tool_function(self, source):

    print("\tMETADATA_TOOL > METADATA_EXTRACTION_TOOL working…")
  
    _TOOL_PROMPT = """Extract the important metadata entities mentioned in the following text. First, all the follwoing, after that extract other themes that fit the context. Finally, extrct 3 to 5 broad general themes, and write a summary. Use Spanish.

METADATA:
Document Title: <title_of_the_document_generated_by_its_content>

People: <comma_separated_list_of_people's_names>

Places: <comma_separated_list_of_places_names>

Dates: <comma_separated_list_of_places_names>

Events: <comma_separated_list_of_places_names>

Other Metadata: <comma_separated_list_of_places_names>

Specific Themes: <comma_separated_list_of_specific_themes_in_Spanish>

General Themes: <comma_separated_list_with_3_to_5_general_themes_in_Spanish>

Summary: <summary_of_the_document_in_Spanish_in_3-6_sentences>

SOURCE TEXT:

The previous input is as follows:

SOURCE:
{source}
"""

    prompt = ChatPromptTemplate.from_template(f"{_TOOL_PROMPT}")
     
    """
      # Check the DEFAULT_LLM constant, and use it, and the appropriate model.
      if DEFAULT_LLM == "openai":
          llm = ChatOpenAI(model=f"{DEFAULT_LLM_MODEL}")
        
      elif DEFAULT_LLM == "ollama":
          # Replace 'ollama_engine' with the appropriate call to create an ollama engine instance
          llm = ollama_engine(model=f"{DEFAULT_LLM_MODEL}")
      else:
          raise ValueError("Unsupported LLM engine specified.")    

      log_and_print(f"Initializing {self.get_name()} afent {self.lab.get_name()} lab with LLM {DEFAULT_LLM} and model {DEFAULT_LLM_MODEL}",
                    LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
    """
    llm = ChatOpenAI(model=f"gpt-4")

    output_parser = StrOutputParser()   
    chain = prompt | llm | output_parser
    
    output = chain.invoke({"source": f"{source}"})

    return output

  def metadata_qa_tool_function(self, source):

    print("\tMETADATA_TOOL > METADATA_QA_TOOL_FUNCTION working…")

    _TOOL_PROMPT = """Validate the extracted metadata from a document to ensure that the metadata remains faithful to the original content and that all entities and topics suggested are supported within the given context. 

- DO NOT CHANGE THE LANGUAGE OF THE TEXT.
- Do return the the quality assurance evaluation, the revised text, and the original text, as follows:
- REMEMBER DO NOT CHANGE THE LANGUAGE OF THE SOURCE.

Return:

QUALITY ASSURANCE EVALUATION:

METADATA:
   
ORIGINAL TEXT:

The previous inputs were as follows:

{source}
"""

    prompt = ChatPromptTemplate.from_template(f"{_TOOL_PROMPT}")
    

    prompt = ChatPromptTemplate.from_template(f"{_TOOL_PROMPT}")
    
    """
    # Check the DEFAULT_LLM constant, and use it, and the appropriate model.
    if DEFAULT_LLM == "openai":
        llm = ChatOpenAI(model=f"{DEFAULT_LLM_MODEL}")
        
    elif DEFAULT_LLM == "ollama":
        # Replace 'ollama_engine' with the appropriate call to create an ollama engine instance
        llm = ollama_engine(model=f"{DEFAULT_LLM_MODEL}")
    else:
        raise ValueError("Unsupported LLM engine specified.")    

    log_and_print(f"Initializing {self.get_name()} afent {self.lab.get_name()} lab with LLM {DEFAULT_LLM} and model {DEFAULT_LLM_MODEL}",
                  LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
    
    # I know this works.
    """    
    llm = ChatOpenAI(model=f"gpt-4")
    
    output_parser = StrOutputParser()   
    chain = prompt | llm | output_parser
    
    output = chain.invoke({"source": f"{source}"})

    return output
        
  def metadata_implement_qa_suggestions_tool_function(self, source):
  
    print("\tMETADATA_TOOL > METADATA_EXTRACTION_TOOL_FUNCTION working…")

    _TOOL_PROMPT = """Your task is to implement the suggestions from a Quality Assurance assistant on metadata, which reviewed an earlier version of extracted metadata. Return:

REVISED METADATA BASED ON QUALITY ASSURANCE EVALUATION:

REVISED METADATA:

SOURCE TEXT:

The previous input was as follows:

{source}
"""

    prompt = ChatPromptTemplate.from_template(f"{_TOOL_PROMPT}")
    """
    # Check the DEFAULT_LLM constant, and use it, and the appropriate model.
    if DEFAULT_LLM == "openai":
        llm = ChatOpenAI(model=f"{DEFAULT_LLM_MODEL}")
        
    elif DEFAULT_LLM == "ollama":
        # Replace 'ollama_engine' with the appropriate call to create an ollama engine instance
        llm = ollama_engine(model=f"{DEFAULT_LLM_MODEL}")
    else:
        raise ValueError("Unsupported LLM engine specified.")    

    log_and_print(f"Initializing {self.get_name()} afent {self.lab.get_name()} lab with LLM {DEFAULT_LLM} and model {DEFAULT_LLM_MODEL}",
                  LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
    """
    llm = ChatOpenAI(model=f"gpt-4")
    output_parser = StrOutputParser()   
    chain = prompt | llm | output_parser
    
    output = chain.invoke({"source": f"{source}"})

    return output

  def metadata(self, source):
  
    print("\t+++++++++++++++++++++++++++++++++++")
    print("\tMETADATA_TOOL: STARTING UP")

    # Define the tools for the Language Graph for this Metadata Extraction Tool
    print("\tDefining LAB > METADATA_TOOL > metadata_extraction_tool")
    self.metadata_extraction_tool = StructuredTool.from_function(
        name="metadata_extraction_tool",
        func=self.metadata_extraction_tool_function,
        description="Extracts metadata from a source by identifying relevant entities. Requires SOURCE TEXT.",
        handle_tool_error=True,
        verbose=True
    )

    print("\tDefining LAB > METADATA_TOOL > metadata_qa_tool")
    self.metadata_qa_tool = StructuredTool.from_function(
        name="metadata_qa_tool",
        func=self.metadata_qa_tool_function,
        description="Performs a quality assurance check of extracted metadata, offering suggestions for enhancement. Input needed METADATA and SOURCE TEXT.",
        handle_tool_error=True,
        verbose=True  
    )

    print("\tDefining LAB > METADATA_TOOL > metadata_implement_qa_suggestions_tool")
    self.metadata_implement_qa_suggestions_tool = StructuredTool.from_function(
      name="metadata_implement_qa_suggestions_tool",
      func=self.metadata_implement_qa_suggestions_tool_function,
      description="Implements QA suggestions to further improve extracted metadata. Input needed QA EVALUATION, METADATA, and SOURCE TEXT.",
      handle_tool_error=True,
      verbose=True
    )

    # Gotta create a Tools array
    self.tools = [
         self.metadata_extraction_tool,
         self.metadata_qa_tool,
         self.metadata_implement_qa_suggestions_tool
    ]

    print(f"{self.tools}")
    self.create_langraph()
    
    print("LANGRAPH CREATED")
    self.workflow.add_node("metadata_extraction_tool", self.metadata_extraction_tool_function)
    self.workflow.add_node("metadata_qa_tool", self.metadata_qa_tool_function)
    self.workflow.add_node("metadata_implement_qa_suggestions_tool", self.metadata_implement_qa_suggestions_tool_function)

    # Set the entrypoint as `agent`
    # This means that this node is the first one called
    self.workflow.set_entry_point("agent")

    # We now add a conditional edge
    self.workflow.add_conditional_edges(
    # First, we define the start node. We use `agent`.
    # This means these are the edges taken after the `agent` node is called.
    "agent",
    # Next, we pass in the function that will determine which node is called next.
    self.should_continue,
    # Finally we pass in a mapping.
    # The keys are strings, and the values are other nodes.
    # END is a special node marking that the graph should finish.
    # What will happen is we will call `should_continue`, and then the output of that
    # will be matched against the keys in this mapping.
    # Based on which one it matches, that node will then be called.
    {
        # If `tools`, then we call the tool node.
        "continue": "tools",
        "metadata_extraction_tool": "metadata_extraction_tool",
        "metadata_qa_tool": "metadata_qa_tool",
        "metadata_implement_qa_suggestions_tool": "metadata_implement_qa_suggestions_tool",
        # Otherwise we finish.
        "exit": END
      }
    )

    # We now add a normal edge from `tools` to `agent`.
    # This means that after `tools` is called, `agent` node is called next.
    self.workflow.add_edge('tools', 'agent')
    self.workflow.add_edge('metadata_extraction_tool', 'metadata_qa_tool')
    self.workflow.add_edge('metadata_qa_tool', 'metadata_implement_qa_suggestions_tool')
    self.workflow.add_edge('metadata_implement_qa_suggestions_tool', 'agent')
    
    self.compile_langraph()
    final_output = ""
    
    _TOOL_TEMPLATE = f"""Extract metadata from the source, undertake quality assurance on the METADATA, and implement recommended changes to the METADATA.

You have 3 tools:

1. metadata_qa_tool: Extracts metadata
2. metadata_qa_tool:  Assesses quality of extracted metadata
3. metadata_implement_qa_suggestions_tool: Integrates QA feedback on metadata

When invoking each tool, provide the full context of previous tools, for reference by the new tool.

After you are done with the tools, please return only the FINAL METADATA BASED ON QUALITY ASSURANCE EVALUATION, without the back and forth. Your supervisor just wants the end result, not the full conversation history. 

- REMEMBER DO NOT CHANGE THE LANGUAGE OF THE SOURCE. IT IS IN SPANISH. 
- YOUR WORKING LANGUAGE IS SPANISH
- Maintain the source language (Spanish) throughout the process.[/INT]

The previous input is as follows:

{source}
"""

    for output in self.chain.stream(
           {"input": f"""{_TOOL_TEMPLATE}""", 
           "intermediate_steps": []}
       ):

       for key, value in output.items():

        print(f"\n\tOutput from METADATA TOOL Node '{key}':")
        
        # Print original input
        if "input" in value:  
          # print("Original Input:", value["input"])
          pass

        agent_outcome = value.get("agent_outcome")

        if agent_outcome is None:
          continue 

        # Print summary for AgentFinish
        if isinstance(agent_outcome, AgentFinish):
          final_output=agent_outcome.return_values["output"]

        # Print details for AgentAction
        elif isinstance(agent_outcome, AgentAction):
          # print("Agent Prompt:", agent_outcome.log)
          print("\tTool invoked:", agent_outcome.tool)  
          #print("Tool Input:", agent_outcome.tool_input)
    
          # Print intermediate steps  
          for step in value["intermediate_steps"]:
            # print("Intermediate Step:")
            # print(step.tool, step.tool_input)
            pass
            
        print()

    self.destroy_langraph()
    
    return final_output

  def __init__(self, lab, name):
      
    # Explicitly call parent init
    super().__init__(lab, name)  
    
    # No params required, handled by metaclass
    log_and_print(f"{self.get_name()} in {self.lab.get_name()} initialized. ",
                  LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

    print("\tDefining LAB > metadata_tool")
    self.tool = StructuredTool.from_function(
        name="metadata_tool",
        func=self.metadata,
        description="Extracts metadata from a source.",
        handle_tool_error=True,
        verbose=True
    )