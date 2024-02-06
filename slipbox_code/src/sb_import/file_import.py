#src/sb_import/file_import

# Import SlipBox’s common functions and constants.
from src.common import *

from pathlib import Path
from pydantic import BaseModel

class file_import(BaseModel):
  # filepath: Path
  # text: str
  # metadata: Dict[str, str]

  @property
  def filepath(self) -> Path:
    #  return self._filepath
    pass
  
  @filepath.setter
  def filepath(self, path: Path) -> None:
    # self._filepath = path
    pass

  def save(self) -> 'ImportFile':
    pass
    return self