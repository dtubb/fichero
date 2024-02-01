import spacy

nlp = spacy.load("es_core_news_sm")
doc = nlp("""
STAMP
REPUBLICA DE COLOMIBA
EX PAPEL SELLADOX
TIMBRE NACIOANL
[[VEINTE CENTAVOS]]

Conste por el presente documento, que yo, Manuel María Lozano, mayor de edad y vecino de este distrito, me constituyo deudor del Dr. C.A.P. de la Torre, por la cantidad de ciento siete pesos ($107.00) moneda legal, por valor de artículos de comercio que de él he recibido a mi satisfacción. Esta cantidad me comprometo a pagarla al Sr. De la Torre o a quien él ceda este documento, dentro del improrrogable término de tres meses a partir de esta fecha y en caso de incumplimiento pagaré el interés del dos por ciento mensual, obligándome a hacerle escritura de hipoteca al Dr. De la Torre sobre una casa de mi propiedad, una vez vencido el plazo para el pago. En constancia firmo el presente en Condoto, a veinte de agosto de mil novecientos veintinueve, ante testigos.

**UNCLEAR SIGNATURE**

TESTIGOS:

**UNCLEAR SIGNATURE**
**UNCLEAR SIGNATURE**

Páguese es el valor del presente documento y sus intereses al Dr. Luis Enrique Bernat, por igual valor recibido.

Condoto, agosto 20 de 1929.

Dr, de la Torre**SIGNATURE**

**FIVE STAMPS**""")

for ent in doc.ents:
    if(ent.label_ == "PER"):
      print("PERSON", ent.text, ent.start_char, ent.end_char, ent.label_)
    else:
      print("NOT PERSON", ent.text, ent.start_char, ent.end_char, ent.label_)