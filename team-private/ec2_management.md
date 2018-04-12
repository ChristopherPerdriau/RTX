# Rtxdev EC2 Instance management guide

## Starting and Stoping the ec2 instance

To start or stop an ec2 instace do the following:
* follow this [link](http://ec2startstop.saramsey.org/cgi-bin/manage-instances-cgi.py)
* enter the username and password when propted
* look to see that the ec2 instance is not already in the state you want it to be in
* check the bubble next to the instance you wish to alter the state of
* check start (or stop) instance
* enter the instance specific passcode
* click on the submit button

**NOTE:** I don't think it wise to post the passwords or username here on github. If you do not have any of there feel free to email me (Finn) or message me on the isb-ncats slack channel to ask for them.

## Starting docker containers


After starting up the ec2 instance you will need to start up the docker containers you wish to use. First connect to the ec2 instance by entering the following into the terminal:

```
ssh ubuntu@rtxdev.saramsey.org
```

Once you are connected to the ec2 instance the commands you will enter depend on the container you wish to use

### Rtxdev or rtxsteve neo4j containers

To start up the rtxdev or rtxsteve containers use the following commands:

```
sudo docker start rtxdev
sudo docker exec rtxdev service neo4j start
sudo docker exec rtxdev service apace2 start
sudo docker exec rtxdev service RTX_OpenAPI start
```
(If you want to start rtxsteve just type rtxsteve everywhere it says rtxdev)

To get into that docker container, just do this:

```
sudo docker exec -it rtxdev bash
```

or if you want to get into the cypher shell you can do the following:

```
sudo docker exec -it rtxdev bin/cypher-shell
```
(This will ask for a username and password which is the same as the one you use when accessing these through a web browser)

To update the git repo, open a shell in the “rtxdev” container (as described above) and then run the following commands:

```
su - rt
cd /mnt/data/orangeboard/code/NCATS
git pull origin master
```
### SemMedDB or UMLS mySQL containers

If you want to start the SemMedDB and UMLS containers enter the following:

```
sudo docker start semmeddb
sudo docker start umls
```

Then if you wish to get into either container you can enter:

```
sudo docker exec -ti semmeddb bash
```

or if you want to access mysql as the root user simply enter the following:

```
sudo docker exec -ti semmeddb mysql -p
```
(This will ask for a password which is the same as the password for the neo4j instances)

## Open Ports on rtxdev ec2 instance

|port | used for|
|----|------|
|:7474| rtxdev neo4j container HTTP access|
|:7473| rtxdev neo4j container HTTPS access|
|:7687| rtxdev neo4j container BOLT access|
|:7674| rtxsteve neo4j container HTTP access|
|:7673| rtxsteve neo4j container HTTPS access|
|:7887| rtxsteve neo4j container BOLT access|
|:3306| SemMedDB mySQL container|
|:3406| UMLS nySQL container|
