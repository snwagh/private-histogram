# App instructions.
The app takes your private netflix-ish data, stored in `/private/my_data.json`, encrypts it and publishes it, and then the encrypted data of all ring members is aggregated and the average computed and this average result will create a file called `/private/private-histogram/aggregate_data.json` with the average. 

## Pre install steps
Before each party installs app
- Create a `my_data.json` file in /private/ (private is a peer directory to public). Refer to the main.py for what the data should look like.
- Add your _.syftperms to /private/
- Run your client and then run the app and wait for the computation result to be available at `/private/private-histogram/aggregate_data.json` with the average result of everyone's netflix like data. 
