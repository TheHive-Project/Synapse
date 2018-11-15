FROM python:3

WORKDIR /opt/synapse

COPY . .
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5000

CMD [ "python3", "./app.py"]
