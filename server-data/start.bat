@echo off
title TOTK Online Server (Optimized Lightweight)
echo Starting TOTK Online Server with optimized memory settings...
java -Xms128m -Xmx512m -XX:+UseG1GC -XX:+OptimizeStringConcat -XX:+UseStringDeduplication -jar server.jar
pause