import sys
import asyncio
import aiohttp
import time
import json

from config import schedule
from config import models, comparison_models, configure
import support
from comparison import make_comparison

debug = False

def get_comparison_model(i):
  return comparison_models[i % len(comparison_models)]

def get_model(i):
  for model in models:
     if not schedule[model.name]:
       continue
     if i == 0:
       return model
     else:
        i -= 1

def display(trail, text):
  print(text)
  trail.append(text)

async def multi_way_query(prompt, max_models = 10):
  """Query the configured models in parallel and gather the responses. """
  promises = []
  async with aiohttp.ClientSession() as session:

    i = 0
    for model in models:
      if schedule[model.name]:
        promise = model.ask(session, model.make_query(prompt))
        promises.append(promise)
        i += 1
        if i == max_models:
          break

    responses = await asyncio.gather(*promises)
  
  return responses

def clean(str):
  str1 = str.replace("\n", "\\n")
  str2 = str1.replace('"', '\\"')
  return str2

def parse_responses(responses, trail, verbose=False):
  """Parsing out the model specific text field. Display responses if display flag is True"""
  response_texts = []
  i = 0
  for model in models:
    if not schedule[model.name]:
      if debug: display(trail, "skiped " + model.name)
      continue
    if verbose: display(trail, "model " + model.name)
    json_data = json.loads(responses[i])
    json_formatted_str = json.dumps(json_data, indent=2)
    if debug: print(json_formatted_str)
    text = support.search_json(json_data, model.text_field)
    if text != None and text.strip() != "":
      if verbose: display(trail, text)
      response_texts.append(text)
    else:
      if verbose: display(trail, "No response text found!")
      response_texts.append("")
    i += 1
    if i == len(responses):
      break
  return response_texts


async def compare(session, model, comparison, trail, verbose = False):
  query = model.make_query(clean(comparison))
  if debug: print(query)
  response = await model.ask(session, query)
  json_data = json.loads(response)
  if verbose:
    json_formatted_str = json.dumps(json_data, indent=2)
    if debug: print(json_formatted_str)
  text = support.search_json(json_data, model.text_field)
  if text is None:
    if verbose: display(trail, f"comparison using {model.name} failed!")
    return False
  if verbose: display(trail, f"comparison using {model.name} result:\n" + text)

  if text.find("YES") != -1 and not text.find("NO") != -1:
    return True
  else:
    return False

async def compare_one_way(prompt, response_texts, trail, verbose = False):
  """Compare the first two non blank result texts. Return None if no matches"""
  texts = [item for item in response_texts if item.strip() != ""]
  if len(texts) < 2:
    display(trail, "Not enough responses to compare")
    return None
  
  alice = texts[0]
  bob = texts[1]

  comparison = make_comparison(prompt, "Alice", alice, "Bob", bob)
  if verbose: display(trail, comparison)

  async with aiohttp.ClientSession() as session:
    model = get_comparison_model(0)

    if await compare(session, model, comparison, verbose):
        if verbose: display(trail, f"comparison {model.name} succeeds, can use {get_model(0).name}")
        return alice
    else:
        return None
    

async def compare_two_or_three_way(prompt, response_texts, two_way_only, trail, verbose = False):
  """Compare the first 3 non blank result texts 2 or 3 way. Return None if no matches"""
  texts = [item for item in response_texts if item.strip() != ""]
  if len(texts) < 3:
    display(trail, "Not enough responses to compare!")
    return None
  
  # 3 way comparison is possible
  alice = texts[0]
  bob = texts[1]
  eve = texts[2]

  comparison1 =  make_comparison(prompt, "Alice", alice, "Bob", bob)
  if verbose: display(trail, comparison1)

  async with aiohttp.ClientSession() as session:
    model = get_comparison_model(0)
    if verbose: display(trail, "Compare using " + model.name)
    if await compare(session, model, comparison1, verbose):
        if verbose: display(trail, f"comparison {model.name} succeeds, can use {get_model(0).name}")
        return alice
    else:
        comparison2 =  make_comparison(prompt, "Alice", alice, "Eve", eve)
        if verbose: display(trail, comparison2)

        model = get_comparison_model(1)
        if verbose: display(trail, "Compare using " + model.name)

        if await compare(session, model, comparison2, verbose):
          if verbose: display(trail, f"comparison {model.name} succeeds, can use {get_model(0).name}")
          return alice
        else:
           if two_way_only:
             return None
           
           comparison3 =  make_comparison(prompt, "Bob", bob, "Eve", eve)
           if verbose: display(trail, comparison3)

           model = get_comparison_model(2)
           if verbose: display(trail, "Compare using " + model.name)

           if await compare(session, model, comparison3, verbose):
              if verbose: display(trail, f"comparison {model.name} succeeds, can use {get_model(1).name}")
              return bob

    return None

async def compare_all_three(prompt, response_texts, trail, verbose=False):
  """Compare the first 3 non blank result texts in parallel"""
  texts = [item for item in response_texts if item.strip() != ""]
  if len(texts) < 3:
    display(trail, "Not enough responses to compare!")
    return None
 
  alice = texts[0]
  bob = texts[1]
  eve = texts[2]

  comparison1 = make_comparison(prompt, "Alice", alice, "Bob", bob)
  if verbose: 
    display(trail, "Alice and Bob")
    display(trail, comparison1)

  comparison2 = make_comparison(prompt, "Alice", alice, "Eve", eve)
  if verbose: 
    display(trail, "Alice and Eve")
    display(trail, comparison2)
  
  comparison3 = make_comparison(prompt, "Bob", bob, "Eve", eve)
  if verbose: 
    display(trail, "Bob and Eve")
    display(trail, comparison3)
 
  async with aiohttp.ClientSession() as session:
    promises = []
    model = get_comparison_model(0)
    promise = compare(session, model, comparison1, verbose)
    promises.append(promise)

    model = get_comparison_model(1)
    promise = compare(session, model, comparison2, verbose)
    promises.append(promise)

    model = get_comparison_model(2)
    promise = compare(session, model, comparison3, verbose)
    promises.append(promise)

    responses = await asyncio.gather(*promises)

  if verbose:
    display(trail, "Alice and Bob " +  ("agree" if responses[0] else "disagree"))
    display(trail, "Alice and Eve " +  ("agree" if responses[1] else "disagree"))
    display(trail, "Bob and Eve " +  ("agree" if responses[2] else "disagree"))

  if all(responses):
    display(trail, "**concensus**")

  if responses[0]:
    return alice
  if responses[1]:
    return alice
  if responses[2]:
    return bob
  
  return None


async def compare_two_first(prompt, response_texts, trail, verbose=False):
  """Compare 2 non blank result texts first and only use a third if first 3 disagree """
  texts = [item for item in response_texts if item.strip() != ""]
  if len(texts) < 2:
    display(trail, "Not enough responses to compare!")
    return None
 
  alice = texts[0]
  bob = texts[1]

  comparison1 = make_comparison(prompt, "Alice", alice, "Bob", bob)
  if verbose: display(trail, comparison1)

  async with aiohttp.ClientSession() as session:
   
    model = get_comparison_model(0)
    if verbose: display(trail, "Compare first two responses using " + model.name)
    response = await compare(session, model, comparison1, verbose)
    if response:
      display(trail, f"first two models agree, can use {get_model(0).name}")
      return alice
    
    # Get 3rd model text
    i = 0
    text3 = ""
    for model in models:
      if schedule[model.name]:
        if i == 2:
          display(trail, "Query next model " + model.name)
          text3 = await model.ask(session, model.make_query(prompt))
          text3 = text3.strip()
          break
        else:
          i += 1

    if text3 == "":
      display(trail, "3rd model failed to answer!")
      return None
    
    eve = text3
    comparison2 = make_comparison(prompt, "Alice", alice, "Eve", eve)
    if verbose: display(trail, comparison2)
  
    model = get_comparison_model(1)
    if verbose: display(trail, "Compare first and third using " + model.name)
    response = await compare(session, model, comparison2, verbose)
    if response:
      display(trail, f"first and third agree, can use {get_model(0).name}")
      return alice
  
    comparison3 = make_comparison(prompt, "Bob", bob, "Eve", eve)
    if verbose: display(trail, comparison3)

    model = get_comparison_model(2)
    if verbose: display(trail, "Compare second and third using " + model.name)
    response = await compare(session, model, comparison3, verbose)
    if response:
     display(trail, f"second and third agree, can use {get_model(1).name}")
    return bob
  
  display(trail, "none agree")
  return None
   

def n_ways(trail, verbose=False):
  m = []
  pairs = []
  for model in models:
    if schedule[model.name]:
      m.append(model)
  for i in range(len(m) - 1):
    for j in range(i + 1, len(m)):
      if verbose: display(trail, m[i].name + " <-> " + m[j].name)
      pairs.append((m[i], m[j], False))
  return pairs


async def compare_n_way(prompt, response_texts, trail, verbose=False):
  run_models = []
  response_map = {}
  r = 0
  for model in models:
    if schedule[model.name]:
      if debug:
        print("response from " + model.name)
        print(response_texts[r])
      run_models.append(model)
      response_map[model.name] = response_texts[r]
      r += 1
  
  quorums = {}
  promises = []
  comparison_pairs = n_ways(trail, True)
  
  async with aiohttp.ClientSession() as session:

    for comparison_pair in comparison_pairs:
      comparison = make_comparison(prompt, 
                                   "John (using " + comparison_pair[0].name + ")",
                                   response_map[comparison_pair[0].name],
                                   "Jane (using " + comparison_pair[1].name + ")",
                                   response_map[comparison_pair[1].name])
      if verbose: display(trail, comparison)
 
      comparison_model = None
      for cm in comparison_models:
        if cm.name != comparison_pair[0].name and cm.name != comparison_pair[1].name:
          comparison_model = cm
          break
      if comparison_model is None:
        raise "Couldn't find a comparison model to use for n-way comparison"
      else:
        if verbose: display(trail, "comparison model selected: " + comparison_model.name)

      promise = compare(session, comparison_model, comparison, verbose)
      promises.append(promise)

    responses = await asyncio.gather(*promises)

  r = 0
  # go over the comparison results
  for comparison in comparison_pairs:
    model1, model2, compare_result = comparison
    compare_result = responses[r] # record the updated boolean response
    if verbose: display(trail, "comparison " + model1.name + " <--> " + model2.name + " result " + str(compare_result))
    r += 1
    if compare_result:
      quorum = quorums.get(model1.name)
      if quorum is None:
        quorums[model1.name] = quorum = []
      quorum.append(model2.name)
      quorum = quorums.get(model2.name)
      if quorum is None:
        quorums[model2.name] = quorum = []
      quorum.append(model1.name)
  
  # display the largest quorum (first if more than one with same size)
  quorum = None
  quorum_size = 0
  model_count = 0
  for model in run_models:
    model_count += 1
    q = quorums.get(model.name)
    if q is not None and len(q) > quorum_size:
      quorum = model.name
      quorum_size = len(q) + 1

  if quorum is None:
    if verbose: display(trail, "No quorum found. All disagree.")
  else:
    if verbose: display(trail, "quorum " + quorum + " of " + str(quorum_size))
    q = quorums[quorum]
    if verbose: display(trail, quorum)
    for model_name in q:
      if verbose: display(trail, model_name)
    if quorum_size == model_count:
      if verbose: display(trail, "**concensus**")
      return response_map[quorum]
    elif quorum_size > model_count / 2:
      if verbose: display(trail, "**quorum majority achieved**")
      return response_map[quorum]
    elif quorum_size == 2:
       if verbose: display(trail, "two agree")

  return None


async def run_comparison(prompt, action):
  trail = []

  if action == "1-way" or action == "2-1":
    max_models = 2
  elif action in ["2-way", "3-way", "3-all"]:
    max_models = 3
  else:
    max_models = 10

  responses = await multi_way_query(prompt, max_models)

  texts = parse_responses(responses, trail, True)

  compared_text = None

  if action == "1-way":
    compared_text = await compare_one_way(prompt, texts, trail, True)
  elif action == "2-way":
    compared_text = await compare_two_or_three_way(prompt, texts, True, trail, True)
  elif action == "3-way":
    compared_text = await compare_two_or_three_way(prompt, texts, False, trail, True)
  elif action == "2-1":
    compared_text = await compare_two_first(prompt, texts, trail, True)
  elif action == "3-all":
    compared_text = await compare_all_three(prompt, texts, trail, True)
  elif action == "n-way":
    compared_text = await compare_n_way(prompt, texts, trail, True)
  elif action == "none":
    return trail
  else:
    display(trail, "unknown compare action " + action)
    return trail

  if compared_text is not None:
    display(trail, "PASS compared response")
    display(trail, compared_text)
  else:
    display(trail, "FAIL comparison")

  return trail

async def timed_comparison(prompt, action):
  start_time = time.time()

  await run_comparison(prompt, action)

  end_time = time.time()
  print(f"Time taken: {end_time - start_time:.2f} seconds")

async def main():

  if len(sys.argv) > 2:
    action = sys.argv[1]
    prompt = clean(sys.argv[2])
  else:
    print(
"""Usage: python3 multillm.py 3-way|2-way|1-way|none|3-all|n-way query
          -- use given text as a prompt for multiple models and perform a comparison.
             1-way compare two responses
             2-way compare first response with second and third response
             3-way compare three responses to see if any two agree
             2-1 compare 2 responses and go on to a third if first two disagree
             3-all compare three responses all ways
             n-way compare all the responses each way
             none can be used to just query and not do a comparison

          python3 multillm.py xyz input
          -- read input until EOF (Ctrl-D) and use the read input as the prompt with xyz comparison action

          python3 multillm.py xyz interactive
          --- start an interactive loop to read prompts. You can end this using Crtl-C or by typing "bye"
          """)
    exit()

  configure()

  if prompt == "interactive": 
    while True:
      prompt = input("prompt>")
      p = prompt.strip()
      if p == "":
        continue
      if p == "bye":
        break
      
      await timed_comparison(prompt, action)
    return
  
  if prompt == "input":
    prompt = sys.stdin.read()
  
  await timed_comparison(prompt, action)

if __name__ == "__main__":
  asyncio.run(main())
