# AI Voice Sales Engine

## Run the application

1. Create `.env` from `.env.example` and add your Gemini API key.
2. Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

3. Start the FastAPI application:

```powershell
python app.py
```

4. Open the API documentation in your browser:

`http://localhost:8000/docs`

## Run the tests

Keep the application running in one terminal. Open a second terminal in the project folder and run:

```powershell
python -m pytest tests/ -v
```

The tests cover the four required sales-agent scenarios.
