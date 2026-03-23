FROM rust:1.94

COPY aufgabe1/ /usr/src/aufgabe1/


WORKDIR /usr/src/aufgabe1
RUN ls 
RUN pwd
#CMD ["cargo build"]
RUN cargo install --path .
CMD ["aufgabe1"]