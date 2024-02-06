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

set_debug(True)

set_verbose(True)

set_llm_cache(SQLiteCache(database_path=".langchain.db"))

llm = ChatOpenAI(
    temperature=0.0,
    max_tokens=2000,
    max_retries=100,
    model=f"{DEFAULT_LLM}",
)

search = TavilySearchAPIWrapper()
tavily_tool = TavilySearchResults(api_wrapper=search, max_results=5)

tools = [TavilySearchResults(max_results=1)]

NEXT_STEP_TEMPLATE = """You are expert researcher trying answer a question ~500 words. You are asked to answer the following question: {question}

The way you are going to answer the question is as follows:

1. Revise your previous answer using the new information.
    - You should use the previous critique to add important information to your answer.
        _ You MUST include from 5 multimarkdown citations in your revised answer to ensure it can be verified.
        - These must be real wbesites
        - Crucally, fact check your answers. Do not hallucinate. Check websites, check citations, and check claims. Double check publisher information. Double check URLs work. Do not make errors. 
        - Add a "References" section to the bottom of your answer (which does not count towards the word limit). These should be the Chicago 17 Notes format:
            [^1]: John Smith, "Website Article Title," Website Name, last modified July 16, 2022, accessed January 15, 2024, https://www.example.com.
            [^2]: etc
    - You should use the previous critique to remove superfluous information from your answer and make SURE it is not more than 500 words.
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

INITIAL_ANSWER_TEMPLATE = """You are expert researcher trying answer a question ~500 words. You are asked to answer the following question: {question}

The way you are going to answer the question is as follows:

1. Give a detailed in ~500 words.
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
    lambda x: "exit" if len(x['intermediate_steps']) >= 2 else "continue",
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
    {"question": """Your task is to write me a letter to a university president about the need to ban cellphones on cmapus. you can use this guardian article as inspiration: https://www.theguardian.com/lifeandstyle/2024/jan/17/cellphone-smartphone-bans-schools
    
    What happens when a school bans smartphones? A complete transformation
Teachers say mobile phones make their lives a living hell – so one Massachusetts school barred them

Tik Root
Students prep for lunchtime at Buxton boarding school, which banned smartphones on campus. 
Students prep for lunchtime at Buxton boarding school, which banned smartphones on campus.
When the weather is nice, the Buxton boarding school moves lunch outside. Students, faculty and guests grab their food from the kitchen, and eat together under a white tent that overlooks western Massachusetts’ Berkshire mountains.

As the close of the school year neared last June, talk turned to final assignments (the English class was finishing Moby-Dick) and end-of-year fun (there was a trip planned to a local lake). It was, in most ways, a typical teenage afternoon – except that no one was on their phones.

Buxton was wrapping up the first year of a simple yet novel experiment: banning cellphones on campus. Or, rather, smartphones.

Instead, the school gave everyone on campus – including staff – a Light Phone, that is, a “dumb” phone with limited functionality. The devices can make calls, send texts (slowly) and can’t load modern applications; instead coming with deliberately cumbersome versions of music and mapping apps. They are about the size of a deck of cards, with black and white screens.

As one student put it: “It’s like the demon baby of an iPad and a Kindle.”

Most everyone agrees, however, that the school is better off with these hell devices. (And yes, that includes students.) There are fewer interruptions during class, more meaningful interactions around campus, and less time spent on screens.

“It’s a problem we’ve found a pretty good way to address,” Scott Hunter, who teaches English and music, said of smartphones. Bea Sas, a senior at Buxton, added: “I think people are a lot more social.”

A student decorates a piece during a ceramics class, while other students interact during an art block at Buxton school.
A student decorates a piece during a ceramics class, while other students interact during an art block at Buxton school.
For many teachers, their students’ phone use is exasperating. “It’s every class, every period,” said Mark McLaughlin, a math teacher at Neah-Kah-Nie high school in Oregon. “The worst part of my job is being the cellphone police.”

Educators across the country report waging a near-constant battle against phones. A survey of a school district in Virginia found that about a third of teachers were telling students to put away their cellphones five to 10 times a class, and 14.7% did so more than 20 times a class.

When a middle school in Canada surveyed staff, 75% of respondents thought that cellphones were negatively affecting their students’ physical and mental health. Nearly two-thirds believed the devices were adversely affecting academic performances as well.

“It’s a big issue,” said Arnold Glass, a professor of psychology at Rutgers University who has researched the impact of cellphones on student performance. “They lose anywhere between a half and whole letter grade if they are allowed to consult their phones in class.”

Ian Trombulak, a guidance counselor at Lamoille Union high school in northern Vermont, is also facing a flood of cellphones at his school. “I have kids who during the day get a Snapchat or text and it ruins their entire day,” he said. Another issue he’s seeing is that students use cellphones to coordinate mass trips to the bathroom so they can hang out during class. “It feels like it distracts from the learning that happens on the academic level.”

Lunchtime at Buxton school.
Lunchtime at Buxton school.
When I mentioned the Buxton experiment to Trombulak, he was intrigued. One thing it could address, he noted, was the argument from students that they need phones to communicate with their parents. And, he said, teenagers often adapt to new parameters relatively quickly. He remembers a field trip with his students where, at the last minute, everyone learned that cellphones wouldn’t be allowed. At first, the news was apocalyptic.

“They were so upset. They didn’t know how to handle themselves. I was really nervous,” said Trombulak, reliving the drama. But part way through the trip, the kids largely forgot about their phones and, at one point, they self-policed a girl who tried to sneak a phone on to the rope source.

“At the end of the first day, sitting around the campfire, they said, ‘We didn’t think about our phones all day,’” said Trombulak. “That was really cool.”

To an extent, Buxton saw a similar progression through the stages of panic, grief and ultimately some level of acceptance. “When it was announced I practically had a breakdown,” said then senior Max Weeks. And while he’s still not a fan of what he says was a “unilateral” decision to switch to the Light Phone, he said, overall, the experience “hasn’t been as bad as I expected”.

It’s an open secret that students still sneak phones into their rooms on campus, with some testing the limits more than others. “People get pretty ballsy,” said Yamailla Marks, also a Buxton senior, and get caught. Generally, though, it’s hard to spot a smartphone on campus.

That includes staff. The head of the school, Peter Beck, says he gave up his iPhone for a Light Phone and installed an old GPS system in his car for when he needs to go out into the world. He’s thrilled with how the first year has gone. (Beck left the school at the end of the summer).

It’s difficult to tell how the new phone policy is affecting academic performance because Buxton uses a narrative evaluation system. But culturally, Beck says, the move has been transformative, often in small but cumulatively meaningful ways.

“People are engaging in the lounges. They are lingering after class to chat,” said Beck, who estimates that he’s now having more conversations than ever at the school. “All these face-to-face interactions, the frequency has gone through the roof.”

Students learn photography from a teacher at Buxton school.
Students learn photography from a teacher at Buxton school.
Another effect has been a surge of students signing up for the school’s photography class, which uses film cameras. Enrollment nearly tripled. While a popular new teacher may have been a factor, Light Phones also don’t have cameras.

Sign up to Reclaim your brain
A five-week coaching program to help you scroll less and live more
Privacy Notice: Newsletters may contain info about charities, online ads, and content funded by outside parties. For more information see our Privacy Policy. We use Google reCaptcha to protect our website and the Google Privacy Policy and Terms of Service apply.
“It’s much more of a process to get photos now than with the phone,” said Marks, but she’s fallen “in love” with photography. Still, when she goes home for breaks it’s back to her smartphone. Then she has to give it up again when she comes back to school. “It’s really funny how you adjust very quickly. Like subconsciously.”

Buxton isn’t alone in trying to curb the use of smartphones in schools. As of 2020, the National Center for Education Statistics reported more than three-quarters of schools in the US had moved to restrict the non-academic use of the devices. France banned smartphone use in schools in 2018. But whether the private schools’ Light Phone approach could – or should – be applied to public schools wrestling with how to handle cellphones is up for debate.

As a parent, Mark’s mother, Nina Marks, has been thrilled by the Buxton experiment. The school picked, and largely won, a fight that she hadn’t been able to with her daughter. But as a teacher, she’s hesitant.

“Children and adolescents have supercomputers in their pockets … It’s a constant battle to deal with,” she said, agreeing with other educators. But, she adds, having to police cellphones has created friction with her students in the past and can single out students in ways that can be problematic. She likes her current school’s policy, which is to let each teacher decide how to handle phones in their classrooms.

Marks isn’t alone in being skeptical of outright bans. A staff survey at a school district in Illinois found that 70% of the 295 respondents thought students should be allowed to have their phones at school. “We aren’t teaching them accountability and responsibility by storing it for the day,” wrote one anonymous commenter.


Trombulak also sees phones as a potential teaching moment for students. “They’re struggling with the phone, but they didn’t invent the phone. They didn’t buy the phone,” he said. “If school is a place you’re supposed to learn how to do things, then safe technology use needs to become more part of the curriculum.”

Providing dumb phones could be part of the way forward, Nina Marks admits, but she wonders if funds at already strapped public schools could be put to better use. “If you think of people as addicts, you have to replace that with something else,” she said. “If there was extra money to go around, rather than buying every kid another device, I would give every kid a journal and some really nice paint markers.”

A student flips through a book at the Arts studio at Buxton School, Williamstown, MA.
A student flips through a book in the arts studio at Buxton school.
Nonetheless, Light Phone has seen interest from other private schools and school groups, intrigued by the Buxton model, as well as organizations such as churches.

The company bills itself as an antidote to smartphone overuse – a non-alcoholic beer of phones. “We’re actually pretty into tech – we built a phone. We’re just not into extractive tech that manipulates your emotional state,” said Joe Hollier, one of the founders. “So many people got a smartphone and didn’t intend to wake up and check their email before they brush their teeth. But that’s what started happening.”

Light Phone is also working on potential tweaks to the design. While Hollier says that Light Phones are intentionally small and slow, so that people use them less, students report that they also break easily and the batteries die quickly, which wasn’t in the plan. They are also debating whether to add the option for a camera, or other features. But, Hollier doesn’t want the broader message to disappear in the details.

“It’s about trying to find a balance that’s appropriate for you, whether that’s a Light Phone, a simplified iPhone or whatever it is,” he advised. “[The goal] is to hopefully remind people that we have the agency to decide how we use these things.”

Student artwork of a flip phone hangs on a wall, and film hangs to dry in a photography class at Buxton school.
Student artwork of a flip phone hangs on a wall, and film hangs to dry in a photography class at Buxton school.
Hollier was among the diners as lunch wound down at Buxton. When the chatter waned, staff and students started making daily announcements. Seniors should meet in the library to go over their graduation speeches. A reminder that prom was just a few days away, followed by a reprimand for whoever stole sparklers from the chemistry lab and a note that the biology class was changing locations.

Then, over the speakers, Can I Call You Rose? by Thee Sacred Souls started to croon. And, on a walkway replete with flowers, a proposal to prom unfurled – they said yes. “The best promposal ever,” cheered one member of the crowd. Another added: “That was soooo good.”

No one caught the moment on camera.

This article was amended on 17 January 2024 to correct the spelling of Ian Trombulak’s surname.?""", "intermediate_steps": []}
):
    # stream() yields dictionaries with output keyed by node name
    for key, value in output.items():
        print(f"Output from node '{key}':")
        print("---")
        print(value)
    print("\n---\n")
    
    