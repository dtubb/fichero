Dear Andy,

Yesterday, I procrastinated on my book and our abstract by working on our project.

I wanted to take some time to write out my thoughts, as we can use it as raw material for the paper. 

I turned some of what I did in the `slipbox` code in Langraph and LangChain into cleaner, simpler, Python scripts, so that maybe you can follow along, that do not require GPT-4 and can run locally on a MacBook Pro (M1) with 16 GB of RAM using Ollama. I made some progress, with `mistral:instruct`. 

I went mistral:instruct, because I do not have enough memory for the larger models. While in testing online, larger models like `mixtral:7x8b` work better, I got things working well with mistral:instruct.

There are a few scripts in the folder `langchian_ollama_scripts`. Each does what I did using LangGraph before, but as very simple scripts. They answer the question that Olama and `mistral:instruct` will be useful for us, as long as we break down the tasks into small steps.

Three observations

1. I put together three scripts:

- langraph_ollama_scripts/name_extract.py
- langraph_ollama_scripts/place_extract.py
- langraph_ollama_scripts/summarize.py

Each is basically the same Python scripts, with different prompts. Each loads a text file, extracts some data (names, places, or a concise summary in Spanish), and then saves the JSON to a text file.

2. GPT-4 gives slightly better results, giving a better summary, finding an extra name,  which appears at the bottom of the test document. However, `mistral:instruct` did fine.

3. `mistral:instruct` works *better* at producing JSON output. 
  - GPT-4 worked well, when I used a JSON parser, however that requires a longer prompt, broke mistral:instuct. I solved this with a if statement.

4. I tested the same prompts (or steps) on `mixtral 7x8B` by hand. I need to find an API I can call in the cloud for testing. IT was very good. I can't run it locally, buy maybe you can? If we can, I think we should go with that.

Generally, `mistral:instruct` is decent. **However the prompts really really matter.* The fewer, minor changes, and they don't work or radically change the output. 

My take away, prompts must be as specific as possible.
  - For example, to extract names, a prompt that tells `mistral:instruct` to 'extract names of people' works reliably. But, ask it to be an 'expert in NER' breaks things. In short, for mistral:instruct less is far more. I think what happens is a more complex prompt adds in more context, and then the LLM simply forgets what it's being asked to do. GPT-4, Mixtral:7xB can give better resutls with more detialed insturctions. Not so mistral:instruct. for mistral:instruct, O think the minimum viable prompt is the best bet. 

On workflows, pipelines, agents, and models, I think we're going to get the most mileage by always using the simplest viable tool at each stage, if we're going to operate over 61,000 images, as these prompts running can take seconds per document.

I think the conclusion is:

1. Use Spacey and a specialized model, when possible, e.g. NER, Docuement Areas, etc.

2. If using a LLM, then chain together a multi-step pipeline that uses as few and as simple prompts as possible. This is what my scripts now do. Step 1, Step 2, Step 3, etc.

3. Use LangGraph, agents, assistants, labs, etc for problems where the steps to follow are not knowable in advance. I think, in these situations, agents will be *very* useful. But, I think the computing power/token cost/time required for a program to to these sorts of steps will not be worth it, except at the end. For example, my quality assurance on OCR worked well, but it didn't need a whole lab to be constructed .

Most tasks, that can't be solved with a Spacy and a specialized model, will be able to be solved with chaining together prompts. I think this is crucial.

The way I implemented the OCR and Metadata extraction before, which worked very well, was in LangGraph as a workflow. It worked well, but was super slow, and costs $90.

It's like using a sports car to walk across the street to buy milk at the corner store by first going round the block. Walking would always be better, cheaper, easier, and more transparent.

I think I can imagine workflows later on where we won't know how to solve a task, and at that point an agent/langraph is ideal.

But, for now, I'm convinced, always prefer special models, or a local LLM, or a more expensive LLM, over a multistep agent. 

However, I bet a multistep agent will be able to do magic, to solve certain tasks. 

# LangGraph on Ollama

I tried to get LangGraph running on Ollama, as there was a demo. But, I couldn't get my code working, and I was too lazy to try to work out how the demo worked. Basically, until OpenAI like "functions" can work on Ollama, I think we're stuck. It does seem there is a model (nexusraven) that can do this, I just can't download it. I'll report back, if I get it working. But, my internet is choking on the 7 GB file. 

I have a demo that simplifies the LanGraph code I had working, in the `examples\langraph_ollama` model. But, I get the error: 

"ValueError: Ollama call failed with status code 400. Details: invalid options: functions"

I think there is progress being made by the LangGraph people, but I can't get it working. Maybe with the new model.

# Integration of my code

Andy, I've not tried to think about how how to integrate my code into the code you're working on. 

For two reasons:

1. I do not have a box of documents to play with. I don't have the internet bandwidth in Columbia to download 61,000 images. Maybe you could send me a folder or two, so I can play with them.

2. I think you have a plan to walk the files, load text, load from a json and save to a json. So, for now, I'm going to concentrate on things I understand, until I see a template of I can build on.
 
As I was doing this, it got me thinking, if you look at my: summarize.py, place_extract.py, and name_extract.py scripts, they're very simple. Set up a langchian, and then run some prompts, and return a result. 
  - I wonder if it might make sense to make a simple script that loads prompts from a text file, and then we can chain them together?
  - Now that I've simplified the code, I can see ways of doing this even simpler: 
    - prompt 1, prompt 2, prompt 3, and then apply it.
  - I guess this is what Weasel and Spacy is for. But, I've not gotten to understanding that yet.

In short, I'll let you think about the architect for now A lot of what my slipbox code was doing, was trying to enable what you're doing that in a more efficient way.

But, I think my examples of working with Olama locally, tell us this will be useful

Best,

Daniel