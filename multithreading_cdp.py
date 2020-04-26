# Developed by Bayram Barış Sarı
# E-mail = bayrambariss@gmail.com
# Tel = +90 539 593 7501
#
# This file traverses Cisco network devices with the help of CDP.
# It reads an IP from ip.txt file and starts traversing from there.
# After it connects to that IP, it runs 'show cdp neighbors' and
# extracts the interface names. Then it creates and runs a new
# command for each interface name. For instance:
# 'show cdp neighbors Gig 0/9 detail | include IP'
# If the IP address is not on the list of ip_addresses,
# it adds the IP to the list. This process continues until all the
# IP addresses on the list are traversed.
#
# After IP list created, it is written to the file and then ???????
# For each time an IP is visited, the functions in matching.py work.
# Hostname and domain name of the IP address are found. Then all the
# interface names are found and are abbreviated. Finally, a list
# that contain this kind of lines is created by this file's function:
#
# hostname + '-' + abbreviated interface name + '.' + domain_name + a separator + IP address


import configparser
import re
import time
from multiprocessing.pool import ThreadPool

import paramiko

# take data for ssh connection from credentials.ini file
cfg = configparser.ConfigParser()
cfg.read("credentials.ini")

username = cfg["DEFAULT"]["username"]
password = cfg["DEFAULT"]["password"]
default_domain_name = cfg["DEFAULT"]["domain-name"]
port = cfg["DEFAULT"]["port"]

ip_list = []
hostname_list = []
fqdn_list = []
matched_list = []


def open_session(hostname):
    try:
        print(f"Connected to:{hostname}")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=hostname, port=port, username=username, password=password)
        return ssh, True
    except paramiko.ssh_exception.AuthenticationException:
        print(
            "Authentication to IP:{ip} failed! Please check your hostname, username and password.".format(
                ip=hostname
            )
        )
        return None, False
    except paramiko.ssh_exception.NoValidConnectionsError:
        print(f"Unable to connect to IP:{hostname}")
        return None, False
    except (ConnectionError, TimeoutError):
        print(f"Timeout error occured for IP:{hostname}!")
        return None, False


def extract_cdp_neighbors(ip):
    interface_names = []
    command = "show cdp neighbors"
    # print("This command is going to be executed: '{0}'".format(command))
    # skip first 17 characters, then take the next 17 characters which start with Gi,Te,Vl,Loop or F
    regex = r"^.{17}(\b(Ten|Gig|Loo|Vla).{15})"
    # try to connect to server, if there is no connection, return none
    ssh, connection = open_session(ip)
    if not connection:
        return None
    try:
        _, output, _ = ssh.exec_command(command)
        output = output.read()
        output = output.decode("utf-8")
        # find matching lines in output with regex rule
        matches = re.finditer(regex, output, re.MULTILINE)
        for match in matches:
            # delete the whitespace characters at the end
            temp_interface_name = match.group(1)
            temp_interface_name = temp_interface_name.strip()
            # add the name to the interface_name list
            interface_names.append(temp_interface_name)
        return interface_names
    except paramiko.ssh_exception.SSHException:
        print(
            "Extract CDP Neighbor Function Error:There is an error connecting or establishing SSH session"
        )
        return None
    finally:
        ssh.close()


def neighbor_detail(ip, commands):
    formatted_commands = []
    global ip_list
    # print("Now, this command is going to be executed: '{0}'".format(commands))
    # regular expression rule for finding lines with " IP address: xxx"
    regex = r"(?=[\n\r].*IP address:[\s]*([^\n\r]*))"
    # try to connect to server, if there is no connection, return none
    ssh, connection = open_session(ip)
    if not connection:
        return None
    try:
        channel = ssh.invoke_shell()
        stdin = channel.makefile("wb")
        output = channel.makefile("rb")

        formatted_commands.append("'''")
        for c in commands:
            formatted_commands.append(c)
        formatted_commands.append("'''")
        formatted_commands = "\n".join(formatted_commands)
        stdin.write(str.encode(formatted_commands))
        output = output.read()
        output = output.decode("utf-8")
        stdin.close()
        matches = re.finditer(regex, output, re.MULTILINE)
        i = 1
        for match in matches:
            if match.group(i):
                found_ip = match.group(i)
                # add the found IP if it's not in the list
                if found_ip not in ip_list:
                    ip_list.append(found_ip)
    except paramiko.ssh_exception.SSHException:
        print(
            "Neighbor Detail Function Error:There is an error connecting or establishing SSH session"
        )
    finally:
        ssh.close()


def find_ips(ip):
    commands = []
    interface_names = extract_cdp_neighbors(ip)
    # print(interface_names)
    # if there is no neighbor, continue with the next IP in the ip_addresses list
    if not interface_names:
        return -1
    # for all interface names, find their IP and add to the ip_addresses list
    for name in interface_names:
        commands.append(f"show cdp neighbors {name} detail | include IP")
    commands.append("exit")
    neighbor_detail(ip, commands)


def get_hostname_and_domain_name(ip):
    hostname = None
    domain_name = default_domain_name
    regex_hostname = r"^\bhostname[\s\r]+(.*)$"
    regex_domain_name = r"^ip[\s\r]domain-name[\s\r]+(.*)$"
    # try to connect to server, if there is no connection, return none
    ssh, connection = open_session(ip)
    if not connection:
        return "-1", default_domain_name
    try:
        channel = ssh.invoke_shell()
        stdin = channel.makefile("wb")
        output = channel.makefile("rb")
        stdin.write(
            """
        show run | i hostname
        show run | i domain-name
        exit
        """
        )

        output = output.read()
        output = output.decode("utf-8").splitlines()
        output = "\n".join(output)
        hostname_matches = re.finditer(regex_hostname, output, re.MULTILINE)
        for h in hostname_matches:
            hostname = h.group(1)

        domain_name_matches = re.finditer(regex_domain_name, output, re.MULTILINE)
        for d in domain_name_matches:
            domain_name = d.group(1)

        stdin.close()
        return hostname, domain_name
    except paramiko.ssh_exception.SSHException:
        print("There is an error connecting or establishing SSH session")
    finally:
        ssh.close()


def match_name_with_ip_address(ip, hostname, domain_name):
    temp_data = []
    command = "show ip interface brief | exclude unassigned"
    # print("\nNow, this command is going to be executed: '", command,"'")
    # take the first 25 characters which start with G,T,V,L or F
    regex = r"(^[GTVLF].{22})+(.{16})"
    # try to connect to server, if there is no connection, return none
    ssh, connection = open_session(ip)
    if not connection:
        return None
    try:
        _, output, _ = ssh.exec_command(command)
        output = output.read()
        output = output.decode("utf-8").splitlines()
        output = "\n".join(output)

        # find matching lines in output with regex rule
        matches = re.finditer(regex, output, re.MULTILINE)
        for match in matches:
            # print ("Match: {match}".format(match = match.group()))

            # temp interface means temp interface name
            temp_interface = match.group(1)
            temp_interface = temp_interface.strip()

            # temp ip means the ip number of the temp interface
            temp_ip = match.group(2)
            temp_ip = temp_ip.strip()

            # shortened means the first the characters of the temp interface name
            shortened = temp_interface[0:2]

            # temp no means the numbers at last of the interface name, i.e xxxx1/29 to 1/29, xxxxx3 to 3
            temp_no = []
            # this loop parses the temp interface name from the end and takes the characters for temp no
            for j in range(1, len(temp_interface)):
                if temp_interface[-j] == "/" or temp_interface[-j].isdigit():
                    temp_no.append(temp_interface[-j])

            # temp name means the shortened+numbers of the interface name, i.e TenGigabitEthernet1/1 to Te1_1
            temp_name = shortened + "".join(temp_no[::-1])
            temp_name = temp_name.replace("/", "_")
            # name means this type of data: istnswbb0001-te1_1.euea.corp.bshg.com    IP-Number
            name = f"{hostname}-{temp_name.lower()}.{domain_name}\t{temp_ip}"
            temp_data.append(name)

        return temp_data
    except paramiko.ssh_exception.SSHException:
        print("There is an error connecting or establishing SSH session")
    finally:
        ssh.close()


def write_file(ip):
    global fqdn_list
    hostname, domain_name = get_hostname_and_domain_name(ip)
    if hostname == "-1":
        return -1
    elif not hostname:
        print("Hostname couldn't be found!")
        return -2
    elif hostname not in hostname_list:
        hostname_list.append(hostname)
        print(f"Hostname: {hostname}")
        fqdn = f"{hostname}.{domain_name}"
        fqdn_list.append(fqdn)

        lines_to_write = match_name_with_ip_address(ip, hostname, domain_name)
        for line in lines_to_write:
            matched_list.append(line)
    else:
        print(f"Hostname:{hostname} is in the list of hostnames")
        return -3


def main():
    global ip_list
    # ip for first ssh connection
    with open("ip.txt") as f:
        ip = f.readline()
    ip_list.append(ip)

    pool = ThreadPool(15)
    i = 0

    start = time.time()
    while i < len(ip_list) < 15:
        find_ips(ip_list[i])
        i = i + 1

    while i < len(ip_list):
        limit = i + min(15, (len(ip_list) - i))
        hostnames = ip_list[i:limit]
        pool.map(find_ips, hostnames)
        i = limit

    pool.map(write_file, ip_list)
    pool.close()
    pool.join()

    end = time.time()
    elapsed = (end - start) / 60
    string = f"\nTotal execution time: {elapsed:.7} minutes."
    print(string)

    ip_filename = "found_ips_multithreading_" + ip + ".txt"
    fqdn_filename = "fqdn_multithreading_" + ip + ".txt"
    dns_filename = "dns_multithreading_" + ip + ".txt"
    with open(ip_filename, "w") as ip_file:
        for ip in ip_list:
            ip_file.write(ip + "\n")

    with open(fqdn_filename, "w") as fqdn_file:
        for fqdn in fqdn_list:
            fqdn_file.write(fqdn + "\n")

    with open(dns_filename, "w") as dns_file:
        for match in matched_list:
            dns_file.write(match.strip() + "\n")
        dns_file.write(string)


if __name__ == "__main__":
    main()
