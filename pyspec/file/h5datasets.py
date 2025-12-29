
import h5py
import sys
import os

class h5crawler_error(Exception):
    pass

class h5crawler(object):
    def __init__(self, fileobj):
        if isinstance(fileobj,str):
            self.hfile = h5py.File(fileobj)
        elif isinstance(fileobj, h5py.File):
            self.hfile = fileobj
        else:
            self.hfile = None

    # search elements with key=value. returns full_path
    def search_key(self, search_key, obj=None,kyroot=None):
        self.search_wrapper(search_func=self._search_key_function, pars={'search_key':search_key})
        return self.result

    def _search_key_function(self,pars,child,full_key,key):
        search_key = pars['search_key']
        if key == search_key:
            return full_key
        return False

    # search datasets with 2d shape
    def search_2d(self):
        self.search_wrapper(search_func=self._search_2d_function, pars=None)
        return self.result

    def _search_2d_function(self,pars,child,full_key,key):
        if isinstance(child,h5py.Dataset):
           if len(child.shape) >= 2:
              return [full_key,child.shape]

    def search_wrapper(self, search_func, pars, obj=None,kyroot=None):

        if obj is None:
            obj = self.hfile
            self.result = []
            kyroot='/'

        for ky in obj.keys():
            cky = os.path.join(kyroot,ky)
            child = self.hfile[cky]

            r = search_func(pars,child,full_key=cky,key=ky)

            if r:
                self.result.append(r)

            if not isinstance(child,h5py.Dataset):
                self.search_wrapper(search_func,pars,obj=child,kyroot=cky)

        return self.result


cr = h5crawler(sys.argv[1])

result = cr.search_2d()
#result = cr.search_key('data')
for r in result:
    print(r)

