FROM rust:1.94

COPY ./ /usr/src/aufgabe1/


WORKDIR /usr/src/aufgabe1
#CMD ["cargo build"]
RUN cargo install --path .
CMD ["aufgabe1"]