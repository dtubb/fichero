import logging
import spacy_llm


spacy_llm.logger.addHandler(logging.StreamHandler())
spacy_llm.logger.setLevel(logging.DEBUG)


from spacy_llm.util import assemble


nlp = assemble("config.cfg")
doc = nlp("""Colora
pon $107.00 MIC.
ire, contra Manuel Maria Lozano
L.E. Bernat, cesionaria
condoto
de CAP de la To-
**MISSING**
1929
Ejecutiva
Grupo - 2º
Radicacion 
No 142

371
REPUBLICA DE COLOMBIA
INTENDENCIA NACIONAL DEL CHOCO
DISTRITO JUDICIAL DE CALI
JUZGADO PRIMERO DEL CIRCUITO DE ISTMINA
179 **RED INK**
180 **BLUE INK OVERTOP OF !79**
Demanda **BLANK**
Juicio Ejecutivo **BLANK**
Demandado: **BLANK**
Apoderado: **BLANK**
Demandante: **BLANK**
Apoderado: **BLANK**
Iniciado el **BLANK** de: **BLANK** del 193**BLANK**
Radicado bajo la partida Nº **BLANK**
El Secretario **BLANK**
IMPRENTA OFICIAL, QUIBDÓ.

EJECUTIVO 
79**HANDWRITTEN TOP RIGHT**
DEMANDANTE: L. E. BERNAT, cesionario de C. A. P. de la Torre
DEMANDADO: MANUEL MARIA LOZANO, vecino de Condoto
FECHA DE LA DEMANDA: 4 de diciembre de 1929
!!!!!!!!!!!!!!!!!!!
0000000000000000000
(119) **HAND WRITTEN IN BLUE**
RECONOCIMIENTO DE UN DOCUMENTO
Partes:
L. E. Bernat
Manuel María Lozano
Fecha de la demanda:
de octubre de 1929
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

**FIVE STAMPS**
Señor Juez del Circuito

E. S. D.

LUIS ENRIQUE BERNAT, abogado titulado, mayor y vecino de esta ciudad, a usted atentamente pido:

1o.- Que se sirva señalar día y hora hábiles para que el señor MANUEL MARIA LOZANO, mayor de edad y vecino de Condoto, comparezca a su despacho a reconocer bajo la gravedad del juramento el contenido y firma del documento que acompaño, suscrito por él en Condoto el día 20 de agosto de 1929, ante los testigos Alfonso Heluk y Gerardo, Vega S.

2o.- Que notifique al mismo señor Lozano la cesión o traspaso por valor recibido que parte legítima ha hecho a mi favor del expresado documento, y

3o.- Que si el señor Lozano no comparece en el día y hora fijados por usted, no estorbándoselo algún impedimento de los que suspenden los términos, lo declare confeso al tenor de lo dispuesto en el artículo 700 del código judicial.

Practicadas las diligencias anotadas, usted se servirá ordenar se me entreguen originales para efectos que convienen a mis intereses.

Renuncio notificación favorable.

Istmina, octubre 5 de 1929

R. E. Bernat **SIGNATURE**

**STAMP**
*UNREADABLE TEXT**
**SIGNATURE


**UNCLEAR HAND WRITTEN TEXT FOR MOST OF PAGE**
Condoto, octubre treinta de mil novecientos veintinueve.

Cumplase en todas sus partes la comisión ordenada por el señor Juez del Circuito de Istmina. En consecuencia, fíjese el día treinta y uno de los corriees a la una de la tarde para el reconocimiento del pagaré adjunto, y demás diligencias ordenadas, para lo cual se librara la orden respectiva al señor Manuel María Lozano

ra
Hans
munchen
-DILIGENCIA DE RECONOCIMIENTO..
En Condoto, veintitres de noviembre de mil novecientos veintinueve, estando el Despacho del Juzgado Municipal en horas de audiencia pública, compareció el señor Manuel Maria Lozano, a quien se citó previamente para el reconocimiento del documento, a que se refiere el auto del señor Juez Segundo del Circuito de Istmina.-El señor Juez, previa imposición de los artículos penales sobre perjuros y testigos falsos, en materia civil, le recibió juramento que prestó conforme sus creencias religiosas y prometió bajo su gravedad no faltar a la verdad. Interrogado que fue para que diga si el documento que se le pone de presente, (el cual le fue [**part of the text is missing or illegible**] otorgado por él el veinte de agosto del corriente año, p
CIENTO SIETE PESOS moneda corriente
a favor del Dr. C. A. P. de
la Torre, es legal y corriente en todas sus partes, y si la firma que aparece al pie de dicho escrito y dice: "Manuel Ma. Lozano", es escrita de su puño y letra, EXPUSO: El documento que se acaba de leer, firmado por mí a favor del Dr. C. A. P. de la Torre el veinte [**part of the text is missing or illegible**]

El texto de agosto del año en curso, por la suma de cien y siete pesos de oro, es legal y vigente en todas sus partes. La firma que aparece al pie de este texto, que dice "Manuel Ma. Lozano", está escrita de mi propio puño y letra, la misma que utilizo en todos mis actos públicos y privados. Asimismo, se notificó al Sr. Lozano de la transferencia de crédito realizada por el Dr. C. A. P. de la Torre a favor del Dr. L. E. Bernat, por el mismo valor recibido. Este documento se firma como constancia, hecho por un testigo a petición del exponente debido a su discapacidad física. El Juez, **UNCLEAR**. Debido a la discapacidad física del exponente, Manuel Maria Lozano, un testigo que fue solicitado por él lo firma, **UNCLEAR**.

Las presentes **UNCLEAR**, Ve Rustam, **UNCLEAR**, Geo, Señor, **UNCLEAR** Segundo del **UNCLEAR**, Ishmina, diciembre dos de mil **UNCLEAR** veintimu, Com a solicitar **UNCLEAR** estas **UNCLEAR**, Al interesado. **UNCLEAR** lla raduación, Be place, Ramin Mille, Planica, Diciembre 2, au 1.929, **UNCLEAR** la **UNCLEAR**

**ENVELOPE**

no. 380

Señor
Juez Segundo del Circuito.
Istmine.

Contiene las diligencias relativas al reconocimiento de un pagaré. Constan de cinco fojas escritas y oficio No. 229.

Condoto, noviembre 23 de 1929.
El Secretario,

PARIS
DE COL
C
OME
E. S. D.
LUIS ENRIQUE BERNAT, mayor y de aquí vecino, a usted muy atentamente pido:
Que libre orden de pago a mi favor y en contra de la persona y bienes del señor Manuel María Lozano, mayor y vecino de Condoto en jurisdicción de este circuito, por la suma de ciento siete pesos oro legal colombiano ($107:00), por los intereses de esta cantidad a la rata del dos por ciento (2%) mensual desde el día veinte de noviembre del corriente año y por las costas del presente juicio.

NACIO
CEN
VONAL
Señor Juez del Circuito
Como fundamento de hecho de esta petición presento a usted, otorgado con las formalidades legales y suscrito ante los testigos Gerardo Vega S. y Alfonso Meluk, el pagaré en que el señor Manuel María Lozano se constituye deudor del señor C. A. P. de 18 Torre por la suma por que pido se libre la ejecución, pagaré que el acreedor me endosó por igual valor recibido y que da derecho para cobrar intereses sobre la suma expresada, a la rata del 2%, desde el 20 de noviembre del corriente año, y las diligencias de reconocimiento y ratificación del endoso hecho a mi favor del mercionado instrumento.

Como fundamento de derecho cito los artículos 46 y 47 de la ley 40 de 1907- 1008- 1016 y 1027 del código judicial, 1494, 1496, 1527, 1551, 1602, 1617, 1634, 1646, 1669, 1670 y demás pertinentes del código civil y lo. ley 39 de 1921.

Istmina, diciembre 4 de 1929
R.E. Bernat
**UNCLEAR**
Istimino, **UNCLEAR** site de mil novecientos ventinueve
**UNCLEAR** en suute toes al **UNCLEAR**
Paraca Eakeren Lester
1 del **UNCLEAR**.

DELEGADO
REPUBLICA
Secretaria de Guzgado 1.0 del Circuito
**UNCLEAR**
**UNCLEAR**
A la **UNCLEAR**
CIRCUITO
COLOMBIA
**UNCLEAR**
TENDENCIA NACIONAL
**UNCLEAR**
DEL CHO
Radicado al folio
Partida No. **UNCLEAR**
**UNCLEAR**
Gstmine, 10
**UNCLEAR**
**UNCLEAR**
**UNCLEAR**
3
9
del L. R.
Di
1929
**UNCLEAR**
diciembre diez de mil novecientos veintinueve.
Es práctica establecida en Juzgado y Tribunales que
cuando en algún negocio ha precedido actuación de funcionarios
del poder judicial, seguirán conociendo los mismos Jueces o Magis-
trados de los mismos juicios en que hayan actuado, abonándoseles
en el reparto que inmediatamente siga. De tal manera que estas diligencias deben pasar al señor Juez 20. de este. Circuito, quien ya
conoció de ellas, y abonársele en el reparto siguiente.
Notifiquese y cúmplase
**UNCLEAR**
Jersion Fust aus.
**UNCLEAR**
Dbroll/929.
A las
11 **UNCLEAR**
**UNCLEAR**
**UNCLEAR**
**UNCLEAR**
""")
print(doc.cats)