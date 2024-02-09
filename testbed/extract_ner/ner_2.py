import spacy

nlp = spacy.load("es_core_news_lg")
doc = nlp("""""")

for ent in doc.ents:
    if(ent.label_ == "PER"):
      print(ent.text) # ent.start_char, ent.end_char, ent.label_
      pass
    elif(ent.label_ == "LOC"):
      # print(ent.text)#, ent.start_char, ent.end_char, ent.label_)
      pass
    elif(ent.label_ == "ORG"):
      #print(ent.text)#, ent.start_char, ent.end_char, ent.label_)
      pass
    else:
      #print("NOT PERSON", ent.text, ent.start_char, ent.end_char, ent.label_)
      pass