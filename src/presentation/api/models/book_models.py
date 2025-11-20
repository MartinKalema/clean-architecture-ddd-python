from pydantic import BaseModel, ConfigDict

class BookCreate(BaseModel):
    title: str
    author: str

class BookResponse(BaseModel):
    id: str
    title: str
    author: str
    is_borrowed: bool

    model_config = ConfigDict(from_attributes=True)
