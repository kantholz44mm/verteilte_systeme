FROM gcc:latest AS builder
WORKDIR /app
COPY . .
RUN gcc -o mein_programm main.c