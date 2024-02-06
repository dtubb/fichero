Here is one way to implement the Slip class and subclasses using the suggestions provided:

```python
# sb_slip.py

from abc import ABC, abstractmethod
from datetime import datetime
import uuid

class Slip(ABC):

  def __init__(self, id, text):
    self.id = id
    self.text = text
    self.created = datetime.now()
    self.modified = self.created

  @abstractmethod
  def save(self):
    pass
    
  def save_markdown(self):
    md = f"# {self.title}\n\n{self.text}"
    # save markdown to file

  @classmethod
  def load(cls, id):
    # load slip from file  

  def link_to(self, other):
    print(f"Linking {self.id} to {other.id}")

def generate_id():
   return str(uuid.uuid4())
   
class SourceSlip(Slip):

  def __init__(self, source):
    id = generate_id()
    text = f"# {source.title}\n\n{source.location}"
    super().__init__(id, text)

class TagSlip(Slip):

  def __init__(self, tag):
    id = generate_id()
    text = f"# {tag.name}" 
    super().__init__(id, text)
    
slip1 = SourceSlip(Source("Article", "/path"))
slip2 = TagSlip(Tag("Python"))

slip1.link_to(slip2)
```

Let me know if you would like me to modify or expand on any part of this example implementation.