FROM rust:1.94

COPY ./ /usr/src/aufgabe1/


WORKDIR /usr/src/aufgabe1
EXPOSE 8080/udp
EXPOSE 8090/udp
#CMD ["cargo build"]
RUN cargo install --path .
CMD ["aufgabe1"]