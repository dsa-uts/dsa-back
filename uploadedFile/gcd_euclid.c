#include <stdio.h>
#include <stdlib.h>

euclid(n, m){
    if (n < m){
        int a = n;
        n = m;
        m = a;
    }
    while (m != 0){
        int r = n%m;
        n = m;
        m = r;
    }

    return n;
}
