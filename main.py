from fastapi import FastAPI
import uvicorn
import psycopg2
import jwt
import json
import os

import core.security
from api import auth

ai_Model = True



app = FastAPI()
app.include_router(auth.router)

@app.get("/")
def read_root():
    return {"status": "Surveillance System Online", "version": "1.0"}

try:

    conn = psycopg2.connect("dbname=home_surveillance_db user=postgres password=12345 host=192.168.100.8 port=5432")

    print("✅ SUCCESS: psycopg2-binary is working perfectly!")
    conn.close()
except Exception as e:
    print(f"❌ ERROR: {e}")


if __name__ == '__main__':
    uvicorn.run (app, host='localhost' , port=8001)