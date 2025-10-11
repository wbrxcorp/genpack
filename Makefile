.PHONY: all install clean

PREFIX ?= /usr/local

all: src/genpack-helper.bin src/genpack.py

src/genpack-helper.bin: src/genpack-helper.cpp
	@echo "Compiling genpack-helper.cpp to genpack-helper.bin"
	g++ -std=c++20 -o $@ $< -lmount

install: all
	@echo "Installing genpack-helper binary to $(DESTDIR)$(PREFIX)/bin"
	mkdir -p $(DESTDIR)$(PREFIX)/bin
	cp -a src/genpack-helper.bin $(DESTDIR)$(PREFIX)/bin/genpack-helper
	chown root:root $(DESTDIR)$(PREFIX)/bin/genpack-helper
	chmod +s $(DESTDIR)$(PREFIX)/bin/genpack-helper
	@echo "Installation of genpack-helper complete."

	@echo "Installing genpack to $(DESTDIR)$(PREFIX)/bin"
	mkdir -p $(DESTDIR)$(PREFIX)/bin
	cp src/genpack.py $(DESTDIR)$(PREFIX)/bin/genpack
	@echo "Installation complete."

clean:
	@echo "Cleaning up..."
	rm -f src/genpack-helper.bin
	rm -rf src/__pycache__
