FROM python:3 as synapse_clean
WORKDIR /opt/synapse
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM synapse_clean
WORKDIR /opt/synapse
COPY . .
EXPOSE 5000
CMD [ "python3", "./app.py"]