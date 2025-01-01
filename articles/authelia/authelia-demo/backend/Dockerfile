FROM python:3.12-slim

RUN pip install fastapi uvicorn
COPY src /

ENTRYPOINT [ "uvicorn" ]
CMD [ "main:app", "--host=0.0.0.0" ]
