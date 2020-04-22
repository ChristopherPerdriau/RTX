# Contact

## Maintainers

- Stephen Ramsey, Oregon State University (stephen.ramsey@oregonstate.edu)
- Amy Glen, Oregon State University (glena@oregonstate.edu)

## Bug reports

Please use the GitHub issues page for this project, and add the label `kg2`.

# How to access RTX KG2

## Neo4j read-only endpoint for RTX KG2 as a graph database

http://kg2endpoint.rtx.ai:7474

(contact the KG2 maintainer for the username and password)

## Where to download the RTX KG2 knowledge graph in JSON format

http://rtx-kg2-public.s3-website-us-west-2.amazonaws.com/

# How to build your own RTX KG2

## General notes:

The KG2 build system is designed only to run in an Ubuntu 18.04 environment
(i.e., either (i) an Ubuntu 18.04 host OS or (ii) Ubuntu 18.04 running in a
Docker container with a host OS that has `bash` and `sudo`). Currently, KG2 is
built using a set of `bash` scripts that are designed to run in Amazon's Elastic
Compute Cloud (EC2), and thus, configurability and/or coexisting with other
installed software pipelines was not a design consideration for the build
system. The KG2 build system's `bash` scripts create three subdirectories
`~/kg2-build`, `~/kg2-code`, and `~/kg2-venv` under the `${HOME}` directory of
whatever Linux user account you use to run the KG2 build software (if you run on
an EC2 Ubuntu instance, this directory would by default be `/home/ubuntu`). The
various directories used by the KG2 build system are configured in the `bash`
include file `master-config.shinc`.

Note about atomicity of file moving: The build software is designed to run with
the `kg2-build` directory being in the same file system as the Python temporary
file directory (i.e., the directory name that is returned by the variable
`tempfile.tempdir` in Python). If you modify the KG2 software or runtime
environment so that `kg2-build` is in a different file system from the file
system in which the directory `tempfile.tempdir` resides, then the file moving
operations that are performed by the KG2 build software will not be atomic and
interruption of `build-kg2.py` could then leave a source data file in a
half-downloaded (i.e., broken) state.

## Setup your computing environment

The computing environment where you will be running the KG2 build should be
running Ubuntu 18.04.  Your build environment should have the following *minimum*
specifications:

- 256 GiB of system memory
- 1,023 GiB of disk space in the root file system 
- high-speed networking (20 Gb/s networking) and storage
- ideally, AWS zone `us-west-2` since that is where the RTX KG2 S3 buckets are located

## The KG2 build system assumes there is no MySQL database already present

The target Ubuntu system in which you will run the KG2 build should *not* have MySQL
installed; if MySQL is installed, you will need to delete it using the following
`bash` command, which requires `curl`: (WARNING! Please don't run this command
without first making a backup image of your system, such as an AMI):

    source <(curl -s https://raw.githubusercontent.com/RTXteam/RTX/master/code/kg2/delete-mysql-ubuntu.sh)

The KG2 build system has been tested *only* under Ubuntu 18.04. If you want to
build KG2 but don't have a native installation of Ubuntu 18.04 available, your
best bet would be to use Docker (see Option 3 below). 

## AWS authentication key and AWS buckets

Aside from your host OS, you'll need to have an Amazon Web Services (AWS)
authentication key that is configured to be able to read from the `s3://rtx-kg2`
Amazon Simple Cloud Storage Service (S3) bucket (ask the KG2 maintainer to set
this up), so that the build script can download a copy of the full Unified
Medical Language System (UMLS) distribution.  You will be asked (by the AWS
Command-line Interface, CLI) to provide this authentication key when you run the
KG2 setup script. Your configured AWS CLI will also need to be able to
programmatically write to the (publicly readable) S3 bucket
`s3://rtx-kg2-public` (both buckets are in the `us-west-2` AWS zone). The KG2
build script downloads the UMLS distribution (including SNOMED CT) from the
private S3 bucket `rtx-kg2` (IANAL, but it appears that the UMLS is encumbered
by a license preventing redistribution so I have not hosted them on a public
server for download; but you can get it for free at the
[UMLS website](https://www.nlm.nih.gov/research/umls/) if you agree to the UMLS
license terms) and it uploads the final output file `kg2.json.gz` to the public
S3 bucket `rtx-kg2-public`. Alternatively, you can set up your own S3 bucket to
which to copy the gzipped KG2 JSON file (which you would specify in the
configuration file `master-config.shinc`), or in the file `build-kg2.sh`, you
can comment out the line that copies the final gzipped JSON file to the S3
bucket. You will also need to edit and place a file `RTXConfiguration-config.json` in the
S3 bucket `s3://rtx-kg2/`; this file provides credentials (username, password, and
HTTP URI for Neo4j REST API server) for accessing a RTX KG1 Neo4j endpoint; the
KG2 build system will dump the KG1 graph from that endpoint and will merge that
graph into KG2. As a minimal example of the data format for
`RTXConfiguration-config.json`, see the file
`RTXConfiguration-config-EXAMPLE.json` in this repository code directory (note:
that config file can contain authentication information for additional server
types in the RTX system; those are not shown in the example file in this code
directory). The KG1 Neo4j endpoint need not (and in general, won't be) hosted in
the same EC2 instance that hosts the KG2 build system. Currently, the KG1 Neo4j
endpoint is hosted in the instance `arax.rtx.ai`; the URI of its Neo4j
REST HTTP interface is: `http://arax.rtx.ai:7474`.

## My normal EC2 instance

The KG2 build software has been tested with the following instance type:

- AMI: Ubuntu Server 18.04 LTS (HVM), SSD Volume Type - `ami-005bdb005fb00e791` (64-bit x86)
- Instance type: `r5a.8xlarge` (256 GiB of memory)
- Storage: 1,023 GiB, Elastic Block Storage
- Security Group: ingress TCP packets on port 22 (ssh) permitted

As of summer 2019, an on-demand `r5a.8xlarge` instance in the `us-west-2` AWS
zone costs $1.81 per hour, so the cost to build KG2 (estimated to take 67 hours)
would be approximately $121 (this is currently just a rough estimate, plus or
minus 20%). [Unfortunately, AWS doesn't seem to allow the provisioning of spot
instances while specifying minimum memory greater than 240 GiB; but perhaps soon
that will happen, and if so, it could save significantly on the cost of updating the RTX KG2.]
There is also an experimental Snakemake build system which takes advantage of
symmetric multiprocessing to bring the build time down to 54 hours (Option #2).

## Build instructions

Note: to follow the instructions for Option 2 and Option 3 below, you will need
to be using the `bash` shell on your local computer.

### Option 1: build KG2 serially (about 67 hours) directly on an Ubuntu system:

These instructions assume that you are logged into the target Ubuntu system, and
that the Ubuntu system has *not* previously had `setup-kg2-build.sh` run (if it has
previously had `setup-kg2-build.sh` run, you may wish to clear out the instance by running
`clear-instance.sh` before proceeding, in order to ensure that you are getting the
exact python packages needed in the latest `requirements.txt` file in the KG2 codebase):

(1) Install `git` by running this command in the `bash` shell:

    sudo apt-get update -y && sudo apt-get install -y screen git

(2) change to the user's home directory:

    cd 
    
(3) Clone the RTX software from GitHub:

    git clone https://github.com/RTXteam/RTX.git

(4) Setup the KG2 build system: 

    RTX/code/kg2/setup-kg2-build.sh

Note that there is no need to redirect `stdout` or `stderr` to a log file, when
executing `setup-kg2-build.sh`; this is because the script saves its own `stdout` and
`stderr` to a log file `/home/ubuntu/setup-kg2.log`. This script takes just a
few minutes to complete. The script will ask you to enter your AWS Access Key ID
and AWS Secret Access Key, for an AWS account with access to the private S3
bucket that is configured in `master-config.shinc`. It will also ask you to
enter your default AWS zone, which in our case is normally `us-west-2` (you
should enter the AWS zone that hosts the private S3 bucket that you intend to
use with the KG2 build system).

(5) Look in the log file `/home/ubuntu/setup-kg2-build.sh` to see if the script
completed successfully; it should end with `======= script finished ======`.

(6) Initiate a `screen` session to provide a stable pseudo-tty:

    screen

(7) Within the `screen` session, run:

    bash -x ~/kg2-code/build-kg2.sh all

Then exit screen (`ctrl-a d`). Note that there is no need to redirect `stdout`
or `stderr` to a log file, when executing `build-kg2.sh`; this is because the
script saves its own `stdout` and `stderr` to a log file `build-kg2.log`. You can 
watch the progress of your KG2 build by using this command:

    tail -f ~/kg2-build/build-kg2.log
    
Note that the `build-multi-owl-kg.sh` script also saves `stderr` from running `multi_owl_to_json_kg.py`
to a file `~/kg2-build/build-kg2-owl-stderr.log`.

### Option 2: build KG2 in parallel (about 54 hours) directly on an Ubuntu system:

(1)-(5) Follow steps (1) through (5) from Option 1

(6) Initiate a `screen` session to provide a stable pseudo-tty:

    screen

(7) Within the `screen` session, run:

    ~/kg2-code/build-kg2-snakemake.sh

to generate the full size knowledge graph. Then exit screen (using `ctrl-a d`). Note that there is 
no need to redirect `stdout` or `stderr` to a log file when executing `build-kg2-snakemake.sh`; 
this is because the script saves its own `stdout` and `stderr` to a log file 
(`build-kg2-snakemake.log`, located in the build directory). If you don't want to see all of the 
printouts, but want to know which files have finished, you can look at the log file in `.snakemake/log/` 
(if you have run snakemake before, choose the file named with the date you started the build).

If you want to create a test size graph (about 31 hours), run:

    ~/kg2-code/build-kg2-snakemake.sh test

You can watch the progress of your KG2 build by using this command:

    tail -f ~/kg2-build/build-kg2-snakemake.log
    
Note that the `build-multi-owl-kg.sh` script also saves `stderr` from running `multi_owl_to_json_kg.py`
to a file `~/kg2-build/build-kg2-owl-stderr.log`.

(8) When the build is complete, look for the following line (the 2nd line from
    the bottom) in `build-kg2-snakemake.log` and `.snakemake/log/` file (you only need
    to check one):

    22 of 22 steps (100%) done

If that line is present the Snakefile completed successfully (as more databases are added, 22 could grow to 
a larger number. The important piece is 100%). If any line says:

    (exited with non-zero exit code)

the code failed.

### Option 3: remotely build KG2 in an EC2 instance via ssh, orchestrated from your local computer

This option requires that you have `curl` installed on your local computer. In a
`bash` terminal session, set up the remote EC2 instance by running this command
(requires `ssh` installed and in your path):

    source <(curl -s https://raw.githubusercontent.com/RTXteam/RTX/master/code/kg2/ec2-setup-remote-instance.sh)
    
You will be prompted to enter the path to your AWS PEM file and the hostname of
your AWS instance.  The script should then initiate a `bash` session on the
remote instance. Within that `bash` session, continue to follow the instructions for Option 1 or 2, starting at step (4).

### Option 4: in an Ubuntu container in Docker (UNTESTED, IN DEVELOPMENT)

(1) If you are on Ubuntu and you need to install Docker, you can run this command in `bash` on the host OS:
   
    source <(curl -s https://raw.githubusercontent.com/RTXteam/RTX/master/code/kg2/install-docker.sh)
    
(otherwise, the subsequent commands in this section assume that Docker is installed
on whatever host OS you are running). 

(2) Clone the RTX software into your home directory:

    cd 
    
    git clone https://github.com/RTXteam/RTX.git

(3) Build a Docker image for KG2:
    
    sudo docker build -t kg2 RTX/code/kg2/
    
(4) Setup a container and setup KG2 in it:

    sudo docker run -it --name kg2 kg2:latest su - ubuntu -c "RTX/code/kg2/setup-kg2-build.sh"
    
(If anything goes wrong, look for an error message using `sudo docker exec kg2 "cat setup-kg2.log"`)

(5) Set up a persistent pseudo-tty using `screen`:

    screen
    
(6) Inside the `screen` session, run:
    
    sudo docker exec kg2 "bash -x kg2-code/build-kg2.sh all"

Then exit screen (`ctrl-a d`). You can watch the progress of your KG2 setup using the
following command:

    sudo docker exec -it kg2 "tail -f kg2-build/build-kg2.log"

Note that the `build-multi-owl-kg.sh` script also saves `stderr` from running `multi_owl_to_json_kg.py`
to a file `~/kg2-build/build-kg2-owl-stderr.log` inside the container.

## The output KG

The `build-kg2.sh` script (run via one of the three methods shown above) creates
a JSON file `kg2.json.gz` and copies it to a publicly accessible S3 bucket
`rtx-kg2-public`. You can access the gzipped JSON file via HTTP, as shown here:

    curl https://s3-us-west-2.amazonaws.com/rtx-kg2-public/kg2.json.gz > kg2.json.gz

Or using the AWS command-line interface (CLI) tool `aws` with the command

    aws s3 cp s3://rtx-kg2-public/kg2.json.gz .

The TSV files for the knowledge graph can be accessed via HTTP as well, shown here:

    curl https://s3-us-west-2.amazonaws.com/rtx-kg2-public/kg2-tsv.tar.gz > kg2-tsv.tar.gz

Or using the AWS command-line interface (CLI) tool `aws` with the command

    aws s3 cp s3://rtx-kg2-public/kg2-tsv.tar.gz .

You can access the various artifacts from the KG2 build (config file, log file,
etc.) at the AWS static website endpoint for the 
`rtx-kg2-public` S3 bucket: <http://rtx-kg2-public.s3-website-us-west-2.amazonaws.com/>

## Hosting the KG on a Neo4j instance

In a clean Ubuntu 18.04 AWS instance, run the following commands:

(1) Clone the RTX software from GitHub:

    git clone https://github.com/RTXteam/RTX.git

(2) Install and configure Neo4j, with APOC:

    RTX/code/kg2/setup-kg2-neo4j.sh

(3) Set up the Neo4j password, by navigating your HTTP browser to Neo4j on the server (port 7474)

(4) Load KG2 into Neo4j:

    RTX/code/kg2/tsv-to-neo4j.sh
    
In Step 4, you will be prompted to enter the Neo4j database password that you chose in step (3).

# Credits

Thank you to the many people who have contributed to the development of RTX KG2:

## Code
Stephen Ramsey, Amy Glen, Finn Womack, Erica Wood, Veronica Flores, Deqing Qu, and Lindsey Kvarfordt.

## Advice and feedback
David Koslicki, Eric Deutsch, Yao Yao, Jared Roach, Chris Mungall, Tom Conlin, Matt Brush,
Chunlei Wu, Harold Solbrig, and Will Byrd.

## Funding
National Center for Advancing Translational Sciences (award number OT2TR002520).

