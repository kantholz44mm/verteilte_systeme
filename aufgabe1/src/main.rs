

use std::{env, io::{Error, ErrorKind, Read, Write}, net::{SocketAddr, TcpListener, TcpStream, ToSocketAddrs, UdpSocket}};

const DEFAULT_LISTEN_ADDRESS: &str = "0.0.0.0:8080";
const DEFAULT_SEND_ADDRESS: &str = "127.0.0.1:8090";
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

fn run_udp(operation: Operation, listen_address: SocketAddr, send_address: SocketAddr) -> std::io::Result<()> {

    let socket = UdpSocket::bind(listen_address)?;
    println!("Bound to address: {:?}", socket.local_addr());

    let mut buf = [0u8; 512];

    loop {
        let (amt, _src) = socket.recv_from(&mut buf)?;
        let input = String::from_utf8_lossy(&buf[..amt]).into_owned();
        
        let operand = input.trim().parse::<i64>().map_err(|e| Error::new(ErrorKind::InvalidInput, e))?;
        let result = operation.execute_on_operand(operand);
        let response = result.to_string() + "\n";
        
        println!("Received '{}', answering '{}'!", &input.trim(), result);
        socket.send_to(response.as_bytes(), send_address)?;
    }
}

fn run_tcp(operation: Operation, listen_address: SocketAddr, send_address: SocketAddr) -> std::io::Result<()> {

    let socket = TcpListener::bind(listen_address)?;
    println!("Bound to address: {:?}", socket.local_addr());

    loop {
        let (mut src_stream, _) = socket.accept()?;
        let mut input = String::new();
        src_stream.read_to_string(&mut input)?;

        let operand = input.trim().parse::<i64>().map_err(|e| Error::new(ErrorKind::InvalidInput, e))?;
        let result = operation.execute_on_operand(operand);
        let response = result.to_string() + "\n";

        println!("Received '{}', answering '{}'!", &input.trim(), result);
        let mut send_stream = TcpStream::connect(send_address)?;
        send_stream.set_nodelay(true)?; // disable nagle
        send_stream.write_all(response.as_bytes())?;
        send_stream.flush()?;
    }
}

fn main() -> std::io::Result<()> {
    {
        let listen_address = env::var("LISTEN_ADDRESS").unwrap_or(String::from(DEFAULT_LISTEN_ADDRESS)).to_socket_addrs()?.next().unwrap();
        let send_address = env::var("SEND_ADDRESS").unwrap_or(String::from(DEFAULT_SEND_ADDRESS)).to_socket_addrs()?.next().unwrap();
        let operation = env::var("OPERATION").map_or(DEFAULT_OPERATION, |p| Operation::from(p.as_str()));
        let socket_type = env::var("SOCKETTYPE").map_or(DEFAULT_SOCKETTYPE, |p| SocketType::from(p.as_str()));

        println!("running with configuration:");
        println!("LISTEN_ADDRESS: {:?}", listen_address);
        println!("SEND_ADDRESS: {:?}", send_address);
        println!("OPERATION: {:?}", operation);
        println!("SOCKETTYPE: {:?}", socket_type);

        let runner = if socket_type == SocketType::TCP { run_tcp } else { run_udp };
        loop {
            let result = runner(operation, listen_address, send_address);
            println!("Runner exited with state: {:?}", result);
        }
    }
}