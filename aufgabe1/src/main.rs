#![feature(int_from_ascii)]

use std::{env, io::{Read, Write}, net::{TcpListener, UdpSocket}};

const DEFAULT_LISTEN_PORT: u16 = 8080;
const DEFAULT_OPERATION: Operation = Operation::Increment;
const DEFAULT_SOCKETTYPE: SocketType = SocketType::UDP;

#[derive(Clone, Copy, Debug, PartialEq)]
enum SocketType {
    UDP,
    TCP
}

impl From<&str> for SocketType {
    fn from(value: &str) -> Self {
        match value.to_lowercase().as_str() {
            "tcp" => SocketType::TCP,
            "udp" => SocketType::UDP,
            _ => DEFAULT_SOCKETTYPE
        }
    }
}



#[derive(Clone, Copy, Debug)]
enum Operation {
    Increment,
    Decrement,
    ShiftLeft,
    ShiftRight,
}

impl From<&str> for Operation {
    fn from(value: &str) -> Self {
        match value.to_lowercase().as_str() {
            "inc" | "increment" => Operation::Increment,
            "dec" | "decrement" => Operation::Decrement,
            "shl" | "shiftleft" => Operation::ShiftLeft,
            "shr" | "shiftright" => Operation::ShiftRight,
            _ => DEFAULT_OPERATION
        }
    }
}

impl Operation {
    pub fn execute_on_operand(self, operand: i64) -> i64 {
        match self {
            Operation::Increment => operand + 1,
            Operation::Decrement => operand - 1,
            Operation::ShiftLeft => operand << 1,
            Operation::ShiftRight => operand >> 1,
        }
    }
}


pub fn lex_number(mut input: &str) -> Option<i64> {

    let (sign, consumed_by_sign) = match input {
        _ if input.starts_with('-') => (-1, 1),
        _ if input.starts_with('+') => ( 1, 1),
        _                           => ( 1, 0),
    };

    input = &input[consumed_by_sign..];

    let (radix, consumed_by_radix) = match input {
        _ if input.starts_with("0x") => (16, 2),
        _ if input.starts_with("0b") => ( 2, 2),
        _                            => (10, 0),
    };

    input = &input[consumed_by_radix..];

    let consumed_by_number = input.chars().take_while(char::is_ascii_hexdigit).count();
    let number = u64::from_str_radix(&input[..consumed_by_number], radix).ok()?;

    Some(number as i64 * sign)
}


fn run_udp(port: u16, operation: Operation) -> std::io::Result<()> {

    let socket = UdpSocket::bind(format!("127.0.0.1:{}", port))?;

    loop {
        let mut buf = [0; 256];
        let (amt, src) = socket.recv_from(&mut buf)?;
        let buf = &mut buf[..amt];
        let operand = lex_number(str::from_utf8(buf).unwrap_or("")).unwrap_or(0);
        let result = operation.execute_on_operand(operand);
        let response = result.to_string();
        let response_buffer = response.as_bytes();

        socket.send_to(response_buffer, src)?;
    }
}

fn run_tcp(port: u16, operation: Operation) -> std::io::Result<()> {

    let socket = TcpListener::bind(format!("127.0.0.1:{}", port))?;

    loop {

        let (mut src_stream, _) = socket.accept()?;

        let mut buf = [0; 256];
        let amt = src_stream.read(&mut buf)?;
        let buf = &mut buf[..amt];
        let operand = lex_number(str::from_utf8(buf).unwrap_or("")).unwrap_or(0);
        let result = operation.execute_on_operand(operand);
        let response = result.to_string();
        let response_buffer = response.as_bytes();

        src_stream.write(response_buffer)?;
        src_stream.flush();
    }
}


fn main() -> std::io::Result<()> {
    {
        let listen_port = env::var("LISTEN_PORT").map_or(DEFAULT_LISTEN_PORT, |p| u16::from_str_radix(&p, 10).unwrap_or(DEFAULT_LISTEN_PORT));
        let operation = env::var("OPERATION").map_or(DEFAULT_OPERATION, |p| Operation::from(p.as_str()));
        let socket_type = env::var("SOCKETTYPE").map_or(DEFAULT_SOCKETTYPE, |p| SocketType::from(p.as_str()));

        if socket_type == SocketType::TCP {
            run_tcp(listen_port, operation)
        } else {
            run_udp(listen_port, operation)
        }
    }
}