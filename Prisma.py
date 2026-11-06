"""Inicia o Prisma. Uso: python Prisma.py [--dry-run]"""
import sys

from prisma.main import main

if __name__ == "__main__":
    sys.exit(main())
