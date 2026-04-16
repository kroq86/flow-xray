"""
Standalone list experiment (not the graph debugger).

For the graph-first autodiff / DOT tooling, use the ``flow_xray`` package
(``from flow_xray import Value, …``).
"""

import random


class Gtype:
  length = 0
  el = 0
  key = '0'
  array = []

  def __init__(self, arr):
    self.length = len(self.__dict__)
    self.setAttr(arr)

  def setAttr(self, arr):
    self.array = arr
    for key in range(len(self.array)):
      setattr(self, str(key), self.array[key])
    self.length = len(self.array)
    self.el = self.__dict__['0']

  def nextEl(self):
    if int(self.key) <= self.length - 2:
      self.key = str(int(self.key) + 1)
      self.el = self.__dict__[self.key]
      return self.el
    else:
      self.key = '0'
      self.el = self.__dict__['0']
      return self.el

  def prevEl(self):
    if int(self.key) >= 1:
      self.key = str(int(self.key) - 1)
      self.el = self.__dict__[self.key]
      return self.el
    else:
      self.key = self.length - 1
      self.el = self.__dict__[str(self.length - 1)]
      return self.el

  def delEl(self):
    del (self.__dict__[self.key])
    self.array.remove(self.el)
    self.setAttr(self.array)


i = 0
arr = []
arr2 = []

while i < random.randint(0, 10):
  i += 1
  arr.append(random.randint(-99, 99))
  arr2.append(random.randint(-99, 99))

T = Gtype(arr)
Y = Gtype(arr2)

for _ in range(T.length + Y.length):
  print('T', T.__dict__)
  print('Y', Y.__dict__)
  if (T.el + Y.el) < 0 and Y.length > 0:
    Y.delEl()
    T.delEl()
    Y.nextEl()
  else:
    T.nextEl()
