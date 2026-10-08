#include "QRPortableDecoder.h"
#include "Barcode.h"
#include "ReaderOptions.h"
#include <fstream>
#include <iostream>
#include <vector>
#include <iomanip>
#include <cstdint>
int main(int argc, char** argv) {
 if(argc!=2)return 2;
 std::ifstream file(argv[1],std::ios::binary|std::ios::ate);
 if(!file)return 3;
 auto size=file.tellg(); if(size<8 || size>1536*1536+8){std::cout<<"REJECTED_SIZE\n";return 0;}
 std::vector<uint8_t> data(static_cast<size_t>(size));file.seekg(0);file.read(reinterpret_cast<char*>(data.data()),data.size());
 auto u32=[&](size_t i){return uint32_t(data[i])|(uint32_t(data[i+1])<<8)|(uint32_t(data[i+2])<<16)|(uint32_t(data[i+3])<<24);};
 auto w=u32(0),h=u32(4);
 auto rc=QRPortableDecodeGray(data.data()+8,data.size()-8,w,h,[](const uint8_t* text,size_t length,void*)->int {
   std::cout<<"PAYLOAD ";for(size_t i=0;i<length;i++)std::cout<<std::hex<<std::setfill('0')<<std::setw(2)<<unsigned(text[i]);std::cout<<"\n";return 0;
 },nullptr);
 if(rc==-1)std::cout<<"REJECTED_DIMENSIONS\n";
 else if(rc!=0){std::cout<<"DECODE_ERROR "<<rc<<"\n";return 4;}
}
