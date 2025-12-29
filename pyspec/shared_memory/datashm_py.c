/******************************************************************************
#
#  %W%  %G% CSS
#
#  "pyspec" Release %R%
#
#  Copyright (c) 2012,2014,2015,2016,2020
#  by Certified Scientific Software.
#  All rights reserved.
#
#  Permission is hereby granted, free of charge, to any person obtaining a
#  copy of this software ("pyspec") and associated documentation files (the
#  "Software"), to deal in the Software without restriction, including
#  without limitation the rights to use, copy, modify, merge, publish,
#  distribute, sublicense, and/or sell copies of the Software, and to
#  permit persons to whom the Software is furnished to do so, subject to
#  the following conditions:
#
#  The above copyright notice and this permission notice shall be included
#  in all copies or substantial portions of the Software.
#
#  Neither the name of the copyright holder nor the names of its contributors
#  may be used to endorse or promote products derived from this software
#  without specific prior written permission.
#
#     * The software is provided "as is", without warranty of any   *
#     * kind, express or implied, including but not limited to the  *
#     * warranties of merchantability, fitness for a particular     *
#     * purpose and noninfringement.  In no event shall the authors *
#     * or copyright holders be liable for any claim, damages or    *
#     * other liability, whether in an action of contract, tort     *
#     * or otherwise, arising from, out of or in connection with    *
#     * the software or the use of other dealings in the software.  *
#
******************************************************************************/

#include "sps.h"
#include <Python.h>

struct module_state {
    PyObject* error;
};

#if PY_MAJOR_VERSION >= 3
#define GETSTATE(m) ((struct module_state*)PyModule_GetState(m))
#else
#define GETSTATE(m) (&_state)
static struct module_state _state;
#endif

void initdatashm(void);
static void datashm_cleanup(void);

static char datashm_type2py(int t)
{
    switch (t) {
    case SPS_SHORT:
        return ('h');
    case SPS_USHORT:
        return ('H');
    case SPS_INT:
        return ('i');
    case SPS_UINT:
        return ('I');
    case SPS_LONG:
        return ('k');
    case SPS_ULONG:
        return ('K');
    case SPS_LONG64:
        return ('L');
    case SPS_DOUBLE:
        return ('d');
    case SPS_FLOAT:
        return ('f');
    case SPS_CHAR:
        return ('b');
    case SPS_UCHAR:
        return ('B');

        // returning n for non supported types

    case SPS_STRING:
    case SPS_ULONG64:
    default:
        return ('n');
    }
    return ('n');
}

static PyObject* buildEntry(char ptype, void** ptr)
{
    PyObject* entry;

    double* dptr;
    float* fptr;
    long* lptr;
    long long* llptr;
    int* iptr;
    unsigned int* uiptr;
    short* sptr;
    unsigned short* usptr;
    unsigned long* ulptr;
    char* bptr;
    unsigned char* ubptr;

    if (ptype == 'd') {
        dptr = *ptr;
        entry = Py_BuildValue("d", *dptr);
        dptr++;
        *ptr = dptr;
    } else if (ptype == 'f') {
        fptr = *ptr;
        entry = Py_BuildValue("f", *fptr);
        fptr++;
        *ptr = fptr;
    } else if (ptype == 'i') {
        iptr = *ptr;
        entry = Py_BuildValue("i", *iptr);
        iptr++;
        *ptr = iptr;
    } else if (ptype == 'I') {
        uiptr = *ptr;
        entry = Py_BuildValue("I", *uiptr);
        uiptr++;
        *ptr = uiptr;
    } else if (ptype == 'k') {
        lptr = *ptr;
        entry = Py_BuildValue("k", *lptr);
        lptr++;
        *ptr = lptr;
    } else if (ptype == 'K') {
        ulptr = *ptr;
        entry = Py_BuildValue("K", *ulptr);
        ulptr++;
        *ptr = ulptr;
    } else if (ptype == 'L') {
        llptr = *ptr;
        entry = Py_BuildValue("L", *llptr);
        llptr++;
        *ptr = llptr;
    } else if (ptype == 'h') {
        sptr = *ptr;
        entry = Py_BuildValue("h", *sptr);
        sptr++;
        *ptr = sptr;
    } else if (ptype == 'H') {
        usptr = *ptr;
        entry = Py_BuildValue("H", *usptr);
        usptr++;
        *ptr = usptr;
    } else if (ptype == 'b') {
        bptr = *ptr;
        entry = Py_BuildValue("b", *bptr);
        bptr++;
        *ptr = bptr;
    } else if (ptype == 'B') {
        ubptr = *ptr;
        entry = Py_BuildValue("B", *ubptr);
        ubptr++;
        *ptr = ubptr;
    } else {
        entry = Py_None;
    }

    return entry;
}

static PyObject* datashm_getarraylist(PyObject* self, PyObject* args)
{
    char* spec_version = NULL;
    int i;
    char* array;
    PyObject *list, *string;

    if (!PyArg_ParseTuple(args, "|s", &spec_version)) {
        return NULL;
    }

    list = PyList_New(0);
    for (i = 0; (array = SPS_GetNextArray(spec_version, i)); i++) {
#if PY_MAJOR_VERSION >= 3
        string = PyUnicode_FromString(array);
#else
        string = PyString_FromString(array);
#endif
        PyList_Append(list, string);
        Py_DECREF(string);
    }

    return list;
}

static PyObject* datashm_getspeclist(PyObject* self, PyObject* args)
{
    char* spec_version;
    int i;
    PyObject *list, *string;

    if (!PyArg_ParseTuple(args, "")) {
        return NULL;
    }

    list = PyList_New(0);
    for (i = 0; (spec_version = SPS_GetNextSpec(i)); i++) {
#if PY_MAJOR_VERSION >= 3
        string = PyUnicode_FromString(spec_version);
#else
        string = PyString_FromString(spec_version);
#endif
        PyList_Append(list, string);
        Py_DECREF(string);
    }

    return list;
}

static PyObject* datashm_isupdated(PyObject* self, PyObject* args)
{
    char *spec_version, *array_name;

    if (!PyArg_ParseTuple(args, "ss", &spec_version, &array_name)) {
        return NULL;
    }

#if PY_MAJOR_VERSION >= 3
    return PyLong_FromLong(SPS_IsUpdated(spec_version, array_name));
#else
    return PyInt_FromLong(SPS_IsUpdated(spec_version, array_name));
#endif
}

static PyObject* datashm_getinfo(PyObject* self, PyObject* args)
{
    char *spec_version, *array_name, *ret;

    if (!PyArg_ParseTuple(args, "ss", &spec_version, &array_name)) {
        return NULL;
    }

    ret = SPS_GetInfoString(spec_version, array_name);

    if (ret) {
#if PY_MAJOR_VERSION >= 3
        return PyUnicode_FromString(ret);
#else
        return PyString_FromString(ret);
#endif
    } else {
        struct module_state* st = GETSTATE(self);
        PyErr_SetString(st->error, "Array Info cannot be read");
        return NULL;
    }
}

static PyObject* datashm_getmetadata(PyObject* self, PyObject* args)
{
    char *spec_version, *array_name, *ret;
    u32_t length;

    if (!PyArg_ParseTuple(args, "ss", &spec_version, &array_name)) {
        return NULL;
    }

    ret = SPS_GetMetaData(spec_version, array_name, &length);

    if (ret) {
#if PY_MAJOR_VERSION >= 3
        return PyUnicode_FromString(ret);
#else
        return PyString_FromString(ret);
#endif
    } else {
        struct module_state* st = GETSTATE(self);
        PyErr_SetString(st->error, "Array metadata cannot be read");
        return NULL;
    }
}

static PyObject* datashm_arrayinfo(PyObject* self, PyObject* args)
{
    char *spec_version, *array_name;
    int rows, cols, type, flag;
    int j;

    PyObject *output, *entry;

    if (!PyArg_ParseTuple(args, "ss", &spec_version, &array_name)) {
        struct module_state* st = GETSTATE(self);
        PyErr_SetString(st->error, "Cannot find array.");
        return NULL;
    }

    if (SPS_GetArrayInfo(spec_version, array_name, &rows, &cols, &type, &flag)) {
        struct module_state* st = GETSTATE(self);
        PyErr_Format(st->error,
            "Error getting array info for %s/%s.",
            spec_version, array_name);
        return NULL;
    }

    j = 0;
    output = PyList_New(4);

    entry = Py_BuildValue("i", rows);
    PyList_SetItem(output, j, entry);
    j++;
    entry = Py_BuildValue("i", cols);
    PyList_SetItem(output, j, entry);
    j++;
    entry = Py_BuildValue("i", type);
    PyList_SetItem(output, j, entry);
    j++;
    entry = Py_BuildValue("i", flag);
    PyList_SetItem(output, j, entry);
    j++;

    return output;
}

static PyObject* datashm_getdata(PyObject* self, PyObject* args)
{
    char *spec_version, *array_name;
    int rows, cols, type, flag;
    char ptype;

    int write_flag = 0;

    void* data;

    PyObject *output, *entry;
    PyObject* rowlist;

    int j, k;
    void* ptr;

    if (!PyArg_ParseTuple(args, "ss", &spec_version, &array_name)) {
        return NULL;
    }

    if (SPS_GetArrayInfo(spec_version, array_name, &rows, &cols, &type, &flag)) {
        struct module_state* st = GETSTATE(self);
        PyErr_Format(st->error,
            "Error getting array info for %s/%s.",
            spec_version, array_name);
        return NULL;
    }
    ptype = datashm_type2py(type);

    data = SPS_GetDataPointer(spec_version, array_name, write_flag);
    output = PyList_New(rows);

    ptr = (void*)data;

    if (ptype == 'n') {
        struct module_state* st = GETSTATE(self);
        PyErr_SetString(st->error, "Data type not supported");
        return NULL;
    }

    for (j = 0; j < rows; j++) {
        rowlist = PyList_New(cols);
        for (k = 0; k < cols; k++) {
            entry = buildEntry(ptype, &ptr);
            PyList_SetItem(rowlist, k, entry);
        }
        PyList_SetItem(output, j, rowlist);
    }
    SPS_ReturnDataPointer(data);

    return output;
}

static PyObject* datashm_getdatarow(PyObject* self, PyObject* args)
{
    char *spec_version, *array_name;
    int rows, cols, type, flag;

    char ptype;

    int in_row;
    int nb_copied, j;

    PyObject *output, *entry;
    void* data;
    void* ptr;

    if (!PyArg_ParseTuple(args, "ssi", &spec_version, &array_name, &in_row)) {
        return NULL;
    }

    if (SPS_GetArrayInfo(spec_version, array_name, &rows, &cols, &type, &flag)) {
        struct module_state* st = GETSTATE(self);
        PyErr_SetString(st->error, "Error getting array info");
        return NULL;
    }
    ptype = datashm_type2py(type);

    data = SPS_GetDataRow(spec_version, array_name, type, in_row, 0, &nb_copied);
    output = PyList_New(nb_copied);

    ptr = data;
    for (j = 0; j < nb_copied; j++) {
        entry = buildEntry(ptype, &ptr);
        PyList_SetItem(output, j, entry);
    }

    return output;
}

static PyObject* datashm_getdatacol(PyObject* self, PyObject* args)
{
    char *spec_version, *array_name;
    int rows, cols, type, flag;

    char ptype;

    int in_col;
    int nb_copied, j;

    PyObject *output, *entry;
    void* data;
    void* ptr;

    if (!PyArg_ParseTuple(args, "ssi", &spec_version, &array_name, &in_col)) {
        return NULL;
    }

    if (SPS_GetArrayInfo(spec_version, array_name, &rows, &cols, &type, &flag)) {
        struct module_state* st = GETSTATE(self);
        PyErr_SetString(st->error, "Error getting array info");
        return NULL;
    }
    ptype = datashm_type2py(type);

    data = SPS_GetDataCol(spec_version, array_name, type, in_col, 0, &nb_copied);
    output = PyList_New(nb_copied);

    ptr = data;
    for (j = 0; j < nb_copied; j++) {
        entry = buildEntry(ptype, &ptr);
        PyList_SetItem(output, j, entry);
    }

    return output;
}

static void datashm_cleanup()
{
    SPS_CleanUpAll();
}

static PyMethodDef datashm_methods[] = {
    { "getspeclist", datashm_getspeclist, METH_VARARGS },
    { "getarraylist", datashm_getarraylist, METH_VARARGS },
    { "isupdated", datashm_isupdated, METH_VARARGS },
    { "getdata", datashm_getdata, METH_VARARGS },
    { "getdatarow", datashm_getdatarow, METH_VARARGS },
    { "getdatacol", datashm_getdatacol, METH_VARARGS },
    { "getinfo", datashm_getinfo, METH_VARARGS },
    { "getmetadata", datashm_getmetadata, METH_VARARGS },
    { "getarrayinfo", datashm_arrayinfo, METH_VARARGS },
    { NULL, NULL }
};

#if PY_MAJOR_VERSION >= 3

static int datashm_traverse(PyObject* m, visitproc visit, void* arg)
{
    Py_VISIT(GETSTATE(m)->error);
    return 0;
}

static int datashm_clear(PyObject* m)
{
    Py_CLEAR(GETSTATE(m)->error);
    return 0;
}

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "datashm",
    NULL,
    sizeof(struct module_state),
    datashm_methods,
    NULL,
    datashm_traverse,
    datashm_clear,
    NULL
};

#define INITERROR return NULL

PyObject*
PyInit_datashm(void)

#else

#define INITERROR return

void initdatashm(void)
#endif
{
#if PY_MAJOR_VERSION >= 3
    PyObject* module = PyModule_Create(&moduledef);
#else
    PyObject* module = Py_InitModule("datashm", datashm_methods);
#endif

    if (module == NULL)
        INITERROR;

    struct module_state* st = GETSTATE(module);

    st->error = PyErr_NewException("datashm.Error", NULL, NULL);
    if (st->error == NULL) {
        Py_DECREF(module);
        INITERROR;
    }

    Py_AtExit(datashm_cleanup);

#if PY_MAJOR_VERSION >= 3
    return module;
#endif
}
