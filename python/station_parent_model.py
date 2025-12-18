import jaconv
import pykakasi

kks=pykakasi.kakasi()

def normalize(name):
    res=''
    for item in kks.convert(name):
        res+=item['hira']
    return res
