from yaml import safe_load
import sys
import os


class BaseError(BaseException):
  messages: dict[str, list] = {}
  status: int = 400
  message = None
  
  def __init__(self, message = None, status = None, *args) -> None:
    super().__init__(*args)
    self._load_messages()
    if status:
      self.status = status
    self.message = message
  
  def make_error(self, error, **kwargs):
    message, status = self.messages[error]
    if status:
      self.status = status
    if not self.message:
      self.message = ' '.join(kwargs.get(word, word) for word in message.split())
      
  def _load_messages(self):
    if not os.path.exists(os.getenv('ERROR_MESSAGES')):
      sys.exit(-1)
    with open(os.getenv('ERROR_MESSAGES'), 'r', encoding='utf-8') as f:
      self.messages = safe_load(f)
  
  @property
  def json(self):
    return dict(data=dict(status='error', message=self.message), status=self.status)
  
  def __str__(self):
    return self.message
