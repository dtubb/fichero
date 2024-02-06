## Overall LangGraph (sb\_lab level)

- The sb\_lab LangGraph will represent the high-level conversational workflow between agents

- It will contain nodes for each agent (director, assistants, validator etc) 

- Edges will define the call sequencing between agents

- Conditional edges will route the conversation differently based on agent outputs

- Loops will allow repeated agent calls for iterative workflows

- The sb\_lab\_director agent will coordinate execution based on the graph structure

- Agents are treated as black boxes that accept input and return output
ex  
## Internal Agent LangGraphs

- Agents can optionally construct their own internal LangGraph to represent complex logic

- The internal graph allows multi-step workflows within the agent

- Agents should use internal graphs for logic that is complex, non-linear or involves multiple steps

- Simple single-step agent logic can be implemented directly without a graph

- No changes are needed to agent external interfaces to accommodate internal graphs

## Implementation Details

- The sb\_lab initializes the high-level LangGraph and agents in \_\_init\_\_

- Agent internal graphs are initialized and compiled within the agent classes

- Additional coordination logic is added to sb\_lab\_director to execute the workflow graph

- Agent internal graph inputs and outputs are synchronized to external calls

- Agent state is persisted across graph cycles using class instance variables

## Testing Methodology

- Individual agent graphs can be unit tested by constructing test cases that validate different path outputs


- End-to-end conversation testing can be done by validating full conversation logs for accuracy
