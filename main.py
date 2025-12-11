from fastapi import FastAPI
import uvicorn
import psycopg2
from api import auth,cameras,dashboard,floor,family,unwanted_person,logs

ai_Model = True

app = FastAPI()
app.include_router(auth.router)
app.include_router(cameras.router)
app.include_router(dashboard.router)
app.include_router(floor.router)
app.include_router(family.router)
app.include_router(unwanted_person.router)
app.include_router(logs.router)

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