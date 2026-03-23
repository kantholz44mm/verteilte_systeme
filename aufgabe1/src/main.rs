use std::{env, io::{Read, Write}, net::{IpAddr, Ipv4Addr, TcpListener, TcpStream, UdpSocket}};

const DEFAULT_LISTEN_PORT: u16 = 8080;
const DEFAULT_SEND_ADDRESS: (IpAddr, u16) = (IpAddr::V4(Ipv4Addr::new(127, 0, 0, 1)), 8090);
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


fn run_udp(port: u16, operation: Operation, send_address: (IpAddr, u16)) -> std::io::Result<()> {

    let socket = UdpSocket::bind(format!("127.0.0.1:{}", port))?;

    loop {
        let mut buf = [0; 256];
        let (amt, _src) = socket.recv_from(&mut buf)?;
        let buf = &mut buf[..amt];
        let operand = lex_number(str::from_utf8(buf).unwrap_or("")).unwrap_or(0);
        let result = operation.execute_on_operand(operand);
        let response = result.to_string();
        let response_buffer = response.as_bytes();

        let send_socket = UdpSocket::bind("127.0.0.1")?;
        send_socket.send_to(response_buffer, send_address)?;
    }
}

fn run_tcp(port: u16, operation: Operation, send_address: (IpAddr, u16)) -> std::io::Result<()> {

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

        let mut send_stream = TcpStream::connect(send_address)?;
        send_stream.write(response_buffer)?;
        send_stream.flush();
    }
}

fn parse_address_port_pair(input: &str) -> (IpAddr, u16) {
    let tokens = input.split(":").collect::<Vec<&str>>();

    if tokens.len() != 2 {
        return DEFAULT_SEND_ADDRESS;
    }

    let address = tokens[0].parse::<IpAddr>().unwrap_or(DEFAULT_SEND_ADDRESS.0);
    let port = tokens[1].parse::<u16>().unwrap_or(DEFAULT_SEND_ADDRESS.1);

    (address, port)
}


fn main() -> std::io::Result<()> {
    {
        let listen_port = env::var("LISTEN_PORT").map_or(DEFAULT_LISTEN_PORT, |p| u16::from_str_radix(&p, 10).unwrap_or(DEFAULT_LISTEN_PORT));
        let send_address = env::var("SEND_ADDRESS").map_or(DEFAULT_SEND_ADDRESS, |s| parse_address_port_pair(&s));
        let operation = env::var("OPERATION").map_or(DEFAULT_OPERATION, |p| Operation::from(p.as_str()));
        let socket_type = env::var("SOCKETTYPE").map_or(DEFAULT_SOCKETTYPE, |p| SocketType::from(p.as_str()));

        let runner = if socket_type == SocketType::TCP { run_tcp } else { run_udp };
        loop {
            let result = runner(listen_port, operation, send_address);
            println!("Runner exited with state: {:?}", result);
        }
    }
}