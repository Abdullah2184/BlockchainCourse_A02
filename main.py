from app import app


if __name__ == "__main__":
    import sys

    #Allows the user to specify a port number as a command line argument, 
    # defaulting to 5000 if none is provided
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    app.run(host="0.0.0.0", port=port, debug=False)

        