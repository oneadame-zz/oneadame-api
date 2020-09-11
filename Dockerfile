FROM python:3

ENV ENV PROD

COPY ./requirements.txt /app/requirements.txt

WORKDIR /app

RUN python -m pip install -r requirements.txt

COPY . /app

ENTRYPOINT [ "gunicorn" ]

CMD ["--bind", "0.0.0.0:80", "main:app"]

EXPOSE 80