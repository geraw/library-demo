from garage.garage_sut import app, seed


if __name__ == "__main__":
    seed()
    app.run(host="127.0.0.1", port=5001, debug=False)
