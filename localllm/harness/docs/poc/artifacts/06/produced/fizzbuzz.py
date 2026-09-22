def fizzbuzz(n):
    """
    Return 'Fizz' for multiples of 3, 'Buzz' for multiples of 5,
    'FizzBuzz' for multiples of both, and the string representation
    of n otherwise.
    """
    if n % 15 == 0:
        return 'FizzBuzz'
    elif n % 3 == 0:
        return 'Fizz'
    elif n % 5 == 0:
        return 'Buzz'
    else:
        return str(n)

# test_fizzbuzz.py
def test_fizzbuzz():
    assert fizzbuzz(3) == 'Fizz', 'Test failed for input 3'
    assert fizzbuzz(5) == 'Buzz', 'Test failed for input 5'
    assert fizzbuzz(15) == 'FizzBuzz', 'Test failed for input 15'
    assert fizzbuzz(7) == '7', 'Test failed for input 7'
    print('PASS')

if __name__ == '__main__':
    test_fizzbuzz()
