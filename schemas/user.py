from pydantic import BaseModel

# To create the user
class UserSignup(BaseModel):
    name: str
    username: str
    password: str
    security_question: str
    security_answer: str

#To log in the user
class UserLogin(BaseModel):
    username: str
    password: str

#To forget the password
class UserForgetPassword(BaseModel):
    username: str
    security_question: str
    hashed_security_question: str
    new_password: str

