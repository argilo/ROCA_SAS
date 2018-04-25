#from future.utils import iteritems
#from builtins import bytes
#from past.builtins import basestring
#from past.builtins import long

from functools import reduce

import json
import argparse
import logging
import coloredlogs
import base64
import hashlib
import sys
import os
import re
import math
import itertools
import binascii
import collections
import traceback
import datetime
from math import ceil, log

#            '%(asctime)s %(hostname)s %(name)s[%(process)d] %(levelname)s %(message)s'
LOG_FORMAT = '%(asctime)s [%(process)d] %(levelname)s %(message)s'


logger = logging.getLogger(__name__)
coloredlogs.install(level=logging.INFO, fmt=LOG_FORMAT)




class DlogFprint(object):
    """
    Discrete logarithm (dlog) fingerprinter for ROCA.
    Exploits the mathematical prime structure described in the paper.

    No external python dependencies are needed (for sake of compatibility).
    Detection could be optimized using sympy / gmpy but that would add significant dependency overhead.
    """
    def __init__(self, max_prime=167, generator=65537):
        self.primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97, 101,
                       103, 107, 109, 113, 127, 131, 137, 139, 149, 151, 157, 163, 167]

        self.max_prime = max_prime
        self.generator = generator
        self.m, self.phi_m = self.primorial(max_prime)

        self.phi_m_decomposition = DlogFprint.small_factors(self.phi_m, max_prime)
        self.generator_order = DlogFprint.element_order(generator, self.m, self.phi_m, self.phi_m_decomposition)
        self.generator_order_decomposition = DlogFprint.small_factors(self.generator_order, max_prime)
        logger.debug('Dlog fprint data: max prime: %s, generator: %s, m: %s, phi_m: %s, phi_m_dec: %s, '
                     'generator_order: %s, generator_order_decomposition: %s'
                     % (self.max_prime, self.generator, self.m, self.phi_m, self.phi_m_decomposition,
                        self.generator_order, self.generator_order_decomposition))

    def fprint(self, modulus):
        """
        Returns True if fingerprint is present / detected.
        :param modulus:
        :return:
        """
        if modulus <= 2:
            return False

        d = DlogFprint.discrete_log(modulus, self.generator, self.generator_order, self.generator_order_decomposition, self.m)
        print(d)
        return d is not None

    def primorial(self, max_prime=167):
        """
        Returns primorial (and its totient) with max prime inclusive - product of all primes below the value
        :param max_prime:
        :param dummy:
        :return: primorial, phi(primorial)
        """
        mprime = max(self.primes)
        if max_prime > mprime:
            raise ValueError('Current primorial implementation does not support values above %s' % mprime)

        primorial = 1
        phi_primorial = 1
        for prime in self.primes:
            primorial *= prime
            phi_primorial *= prime - 1
        return primorial, phi_primorial

    @staticmethod
    def prime3(a):
        """
        Simple trial division prime detection
        :param a:
        :return:
        """
        if a < 2:
            return False
        if a == 2 or a == 3:
            return True  # manually test 2 and 3
        if a % 2 == 0 or a % 3 == 0:
            return False  # exclude multiples of 2 and 3

        max_divisor = int(math.ceil(a ** 0.5))
        d, i = 5, 2
        while d <= max_divisor:
            if a % d == 0:
                return False
            d += i
            i = 6 - i  # this modifies 2 into 4 and vice versa

        return True

    @staticmethod
    def is_prime(a):
        return DlogFprint.prime3(a)

    @staticmethod
    def prime_factors(n, limit=None):
        """
        Simple trial division factorization
        :param n:
        :param limit:
        :return:
        """
        num = []

        # add 2, 3 to list or prime factors and remove all even numbers(like sieve of ertosthenes)
        while n % 2 == 0:
            num.append(2)
            n = n // 2

        while n % 3 == 0:
            num.append(3)
            n = n // 3

        max_divisor = int(math.ceil(n ** 0.5)) if limit is None else limit
        d, i = 5, 2
        while d <= max_divisor:
            while n % d == 0:
                num.append(d)
                n = n // d

            d += i
            i = 6 - i  # this modifies 2 into 4 and vice versa

        # if no is > 2 i.e no is a prime number that is only divisible by itself add it
        if n > 2:
            num.append(n)

        return num

    @staticmethod
    def factor_list_to_map(factors):
        """
        Factor list to map factor -> power
        :param factors:
        :return:
        """
        ret = {}
        for k, g in itertools.groupby(factors):
            ret[k] = len(list(g))
        return ret

    @staticmethod
    def element_order(element, modulus, phi_m, phi_m_decomposition):
        """
        Returns order of the element in Zmod(modulus)
        :param element:
        :param modulus:
        :param phi_m: phi(modulus)
        :param phi_m_decomposition: factorization of phi(modulus)
        :return:
        """
        if element == 1:
            return 1  # by definition

        if pow(element, phi_m, modulus) != 1:
            return None  # not an element of the group

        order = phi_m
        for factor, power in list(phi_m_decomposition.items()):
            for p in range(1, power + 1):
                next_order = order // factor
                if pow(element, next_order, modulus) == 1:
                    order = next_order
                else:
                    break
        return order

    @staticmethod
    def chinese_remainder(n, a):
        """
        Solves CRT for moduli and remainders
        :param n:
        :param a:
        :return:
        """
        sum = 0
        prod = reduce(lambda a, b: a * b, n)

        for n_i, a_i in zip(n, a):
            p = prod // n_i
            sum += a_i * DlogFprint.mul_inv(p, n_i) * p
        return sum % prod

    @staticmethod
    def mul_inv(a, b):
        """
        Modular inversion a mod b
        :param a:
        :param b:
        :return:
        """
        b0 = b
        x0, x1 = 0, 1
        if b == 1:
            return 1
        while a > 1:
            q = a // b
            a, b = b, a % b
            x0, x1 = x1 - q * x0, x0
        if x1 < 0:
            x1 += b0
        return x1

    @staticmethod
    def small_factors(x, max_prime):
        """
        Factorizing x up to max_prime limit.
        :param x:
        :param max_prime:
        :return:
        """
        factors = DlogFprint.prime_factors(x, limit=max_prime)
        return DlogFprint.factor_list_to_map(factors)

    @staticmethod
    def discrete_log(element, generator, generator_order, generator_order_decomposition, modulus):
        """
        Simple discrete logarithm
        :param element:
        :param generator:
        :param generator_order:
        :param generator_order_decomposition:
        :param modulus:
        :return:
        """
        if pow(element, generator_order, modulus) != 1:
            # logger.debug('Powmod not one')
            return None

        moduli = []
        remainders = []
        for prime, power in list(generator_order_decomposition.items()):
            prime_to_power = prime ** power
            order_div_prime_power = generator_order // prime_to_power  # g.div(generator_order, prime_to_power)
            g_dash = pow(generator, order_div_prime_power, modulus)
            h_dash = pow(element, order_div_prime_power, modulus)
            found = False
            for i in range(0, prime_to_power):
                if pow(g_dash, i, modulus) == h_dash:
                    remainders.append(i)
                    moduli.append(prime_to_power)
                    found = True
                    break
            if not found:
                # logger.debug('Not found :(')
                return None

        ccrt = DlogFprint.chinese_remainder(moduli, remainders)
        print(ccrt)
        return ccrt


import math
from Crypto.PublicKey import RSA

def checkprime():
    i = 0
    n = [2]
    x = 39

    while len(n) < x:
        i += 1
        for j in range(2, i):
            if math.fmod(i, j) != 0:
                if j == i - 1:
                    n.append(i)
            else:
                break

    #print(n)
    #print(len(n))

    return n

def calcM(n):
    M = 1
    for i in range(0, len(n)):
        M = M * n[i]

    print('-----------M------------------')
    print(M)
    return M

if __name__ == "__main__":
    m = calcM(checkprime())
    c = DlogFprint()
    d = DlogFprint.fprint(c, m)
    #print(c)
