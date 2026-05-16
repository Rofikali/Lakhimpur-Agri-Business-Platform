from fastapi import FastAPI

app = FastAPI(
    title="Lakhimpur Biz API",
    version="0.1.0",
)


@app.get("/")
async def root():
    return {"message": "API Running"}


@app.get("/health")
async def health():
    return {"status": "ok"}
